"""Testy E01-E03 na rzeczywistym SQLite, bez usług zewnętrznych."""
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
import KI

class EContractTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store=KI.Store(Path(self.temp.name)/'isolated_e.sqlite3')
        self.cfg={'price_matrix_enabled':True,'auto_scan_interval':15,'price_threshold_pct':1.0,
                  'pipeline_enabled':False,'telegram_enabled':False}
        self.start=datetime(2026,10,9,12,0,tzinfo=timezone.utc)

    def snap(self,m,price,ticker='AAA'):
        at=self.start+timedelta(minutes=m)
        return {**KI.opportunity_test_snapshot(at,ticker=ticker,price=price),
                'volume':200000+(m%60)}

    def detect(self,m,price):
        return KI.detect_market(self.store,self.snap(m,price),self.cfg)

    def counts(self):
        with self.store.connection() as c:
            return tuple(c.execute('SELECT COUNT(*) FROM '+t).fetchone()[0]
                         for t in ('observations','baselines','events','opportunities'))

    def test_e01_too_soon_does_not_change_baseline_or_observations(self):
        self.assertEqual(self.detect(2,100)['status'],'BASELINE_CREATED')
        first=self.detect(17,103)
        self.assertEqual(first['price_matrix']['state'],'CANDIDATE')
        before=(self.counts(),self.store.get_baseline('AAA','1h'),self.store.get_price_matrix('AAA'))
        rejected=self.detect(18,150)
        self.assertEqual(rejected['status'],'TOO_SOON')
        after=(self.counts(),self.store.get_baseline('AAA','1h'),self.store.get_price_matrix('AAA'))
        self.assertEqual(before,after)
        unsafe={**self.snap(18,150),'price_matrix':rejected['price_matrix']}
        self.assertFalse(KI.accepted_matrix_snapshot(unsafe))
        self.assertEqual(KI.record_opportunity(self.store,unsafe,'cycle',self.start+timedelta(minutes=18))['state'],'NOT_QUALIFIED')

    def test_e01_out_of_order_rejected_without_writing(self):
        self.detect(2,100);self.detect(17,104)
        before=(self.counts(),self.store.get_price_matrix('AAA'))
        result=self.detect(12,105)
        self.assertEqual(result['status'],'OUT_OF_ORDER')
        self.assertEqual(before,(self.counts(),self.store.get_price_matrix('AAA')))

    def test_e01_market_closed_rejected_without_writing(self):
        self.detect(2,100)
        # .WA -> after 17:00 in Warsaw (15:00 UTC during CEST).
        old=self.store.get_baseline('AAA','1h')
        snap=self.snap(187,110,ticker='AAA.WA')
        first=KI.detect_market(self.store,self.snap(2,100,ticker='AAA.WA'),self.cfg)
        self.assertEqual(first['status'],'BASELINE_CREATED')
        before=self.counts()
        result=KI.detect_market(self.store,snap,self.cfg)
        self.assertEqual(result['status'],'MARKET_CLOSED')
        self.assertEqual(before,self.counts())

    def test_e01_matrix_confirms_from_three_sequential_accepted_readings(self):
        self.detect(2,100)
        self.assertEqual(self.detect(17,103)['price_matrix']['consecutive_reads'],1)
        self.assertEqual(self.detect(32,104)['price_matrix']['consecutive_reads'],2)
        r=self.detect(47,105)
        self.assertEqual(r['status'],'PRICE_CONFIRMED')
        self.assertEqual(r['price_matrix']['consecutive_reads'],3)
        self.assertTrue(KI.accepted_matrix_snapshot({**self.snap(47,105),'price_matrix':r['price_matrix']}))
        self.assertEqual(self.store.get_price_matrix('AAA')['anchor_price'],100)

    def test_e02_freshness_15_minutes_inclusive_and_future_rejected(self):
        snap=self.snap(2,100)
        self.assertTrue(KI.open_hour_fresh(snap,self.start+timedelta(minutes=17)))
        self.assertFalse(KI.open_hour_fresh(snap,self.start+timedelta(minutes=17,seconds=1)))
        self.assertFalse(KI.open_hour_fresh(snap,self.start+timedelta(minutes=1)))
        self.assertFalse(KI.open_hour_fresh(snap,self.start+timedelta(minutes=60)))

    def test_e02_telegram_cannot_use_price_older_than_15_minutes(self):
        snap=self.snap(2,105)
        evidence={'kind':'CONFIRMED_OPPORTUNITY','snapshot':snap}
        self.assertTrue(KI.telegram_movement_confirmed(evidence,self.start+timedelta(minutes=17)))
        self.assertFalse(KI.telegram_movement_confirmed(evidence,self.start+timedelta(minutes=17,seconds=1)))

    def test_e02_staleness_does_not_reset_persistent_matrix_anchor(self):
        self.detect(2,100);self.detect(17,103)
        old=self.store.get_price_matrix('AAA')
        snap={**self.snap(17,103),'price_matrix':old}
        self.assertFalse(KI.two_candle_candidate(snap,self.start+timedelta(minutes=33)))
        self.assertEqual(self.store.get_price_matrix('AAA')['anchor_price'],100)
        self.assertEqual(self.store.get_price_matrix('AAA')['anchor_at'],self.snap(2,100)['acquired_at'])

    def insert_pending_delivery(self):
        now=datetime.now(timezone.utc)
        s=KI.opportunity_test_snapshot(now)
        evidence={'kind':'CONFIRMED_OPPORTUNITY','snapshot':s}
        eid='test_e03'
        self.store.save_section('tickers',[s['ticker']])
        with self.store.transaction() as c:
            c.execute('INSERT INTO observations(ticker,interval,candle_time,acquired_at,candle_status,payload) VALUES(?,?,?,?,?,?)',
                      (s['ticker'],'1h',s['candle_time'],s['acquired_at'],s['candle_status'],KI.json_text(s)))
            c.execute('INSERT INTO events VALUES(?,?,?,?,?)',(eid,s['ticker'],'1h',s['acquired_at'],KI.json_text(evidence)))
            c.execute('INSERT INTO analysis_jobs(event_id,state,updated_at) VALUES(?,?,?)',(eid,'DONE',s['acquired_at']))
            c.execute('INSERT INTO outbox(id,event_id,kind,message,status,created_at) VALUES(?,?,?,?,?,?)',
                      (eid+':analysis',eid,'ANALYSIS','Wiadomość testowa','PENDING',s['acquired_at']))
        return eid+':analysis'

    def delivery_state(self,outbox_id):
        with self.store.connection() as c:
            return tuple(c.execute('SELECT status,attempts,next_attempt_at,last_error FROM outbox WHERE id=?',(outbox_id,)).fetchone()),c.execute('SELECT COUNT(*) FROM delivery_receipts').fetchone()[0]

    def test_e03_disabling_pipeline_pauses_existing_pending_queue(self):
        item=self.insert_pending_delivery()
        self.store.save_section('settings',{'pipeline_enabled':False,'telegram_enabled':True})
        original=self.delivery_state(item)
        self.assertFalse(KI.telegram_delivery_active(self.store))
        self.assertFalse(KI.process_delivery_once(self.store,{'TELEGRAM_BOT_TOKEN':'not-a-token','TELEGRAM_CHAT_ID':'1'},item))
        self.assertEqual(original,self.delivery_state(item))
        self.store.save_section('settings',{'pipeline_enabled':True,'telegram_enabled':True})
        self.assertTrue(KI.telegram_delivery_active(self.store))
        self.assertEqual(original,self.delivery_state(item))
        # No network: database can claim a valid message only after reactivation.
        claim=KI.claim_delivery(self.store,item)
        self.assertIsNotNone(claim)
        self.assertEqual(claim['status'],'PENDING')

    def test_e03_disabling_telegram_also_pauses_and_keeps_history(self):
        item=self.insert_pending_delivery()
        self.store.save_section('settings',{'pipeline_enabled':True,'telegram_enabled':False})
        original=self.delivery_state(item)
        self.assertFalse(KI.process_delivery_once(self.store,{},item))
        self.assertEqual(original,self.delivery_state(item))

    def test_e03_both_services_off_means_no_delivery(self):
        item=self.insert_pending_delivery()
        self.store.save_section('settings',{'pipeline_enabled':False,'telegram_enabled':False})
        self.assertFalse(KI.process_delivery_once(self.store,{},item))
        self.assertEqual(self.delivery_state(item)[0][0],'PENDING')

if __name__=='__main__':
    unittest.main(verbosity=2)
