"""E05: aktywnosc rynkowa potwierdzona realnym przyrostem wolumenu 1h;
izolowana SQLite, zadnych API, bez zmian w bazach uzytkownika.
"""
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
import KI

class E05ActivityTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db=Path(self.tmp.name)/'matrix_e05.sqlite3'
        self.store=KI.Store(self.db)
        self.base=datetime(2026,10,9,12,0,tzinfo=timezone.utc)
        self.cfg={'price_matrix_enabled':True,'auto_scan_interval':15,'price_threshold_pct':2.0,
                  'pipeline_enabled':False,'telegram_enabled':False}

    def snap(self, minute, price, volume, origin='Yahoo OHLC', ticker='XYZ', **changes):
        at=self.base+timedelta(minutes=minute)
        s=KI.opportunity_test_snapshot(at,ticker=ticker,price=price)
        s.update(volume=volume,latest_price_origin=origin)
        s.update(changes)
        return s

    def read(self, minute, price, volume, **kwargs):
        return KI.detect_market(self.store,self.snap(minute,price,volume,**kwargs),self.cfg)

    def test_01_identical_three_reads_cannot_confirm_or_enqueue(self):
        self.read(2,100,100)
        a=self.read(17,105,100)
        b=self.read(32,105,100)
        c=self.read(47,105,100)
        self.assertEqual([x['price_matrix']['consecutive_reads'] for x in (a,b,c)],[0,0,0])
        self.assertTrue(all(x['price_matrix']['activity_verified'] is False for x in (a,b,c)))
        self.assertEqual(c['price_matrix']['state'],'MONITORING')
        s={**self.snap(47,105,100),'price_matrix':c['price_matrix']}
        self.assertFalse(KI.two_candle_confirmation(s,self.base+timedelta(minutes=47)))
        self.assertEqual(KI.record_opportunity(self.store,s,'cycle',self.base+timedelta(minutes=47))['state'],'NOT_QUALIFIED')

    def test_02_new_volume_each_read_confirms_and_survives_restart(self):
        self.read(2,100,100)
        a=self.read(17,105,140)
        b=self.read(32,104,155)
        c=self.read(47,103,175)
        self.assertEqual([x['price_matrix']['consecutive_reads'] for x in (a,b,c)],[1,2,3])
        self.assertEqual(c['price_matrix']['state'],'CONFIRMED')
        self.assertIs(c['price_matrix']['activity_verified'],True)
        s={**self.snap(47,103,175),'price_matrix':c['price_matrix']}
        self.assertTrue(KI.two_candle_confirmation(s,self.base+timedelta(minutes=47)))
        latest=KI.Store(self.db).get_price_matrix('XYZ')
        self.assertEqual(latest['anchor_price'],100)
        self.assertEqual(latest['consecutive_reads'],3)
        self.assertEqual(latest['last_volume'],175)

    def test_03_new_hour_positive_volume_is_third_proof_variant_a(self):
        # 12:32, 12:47, then 13:02 begins the next 1h candle.
        self.read(17,100,10)
        a=self.read(32,104,25)
        b=self.read(47,103,40)
        c=self.read(62,103,8)
        self.assertEqual((a['price_matrix']['consecutive_reads'],b['price_matrix']['consecutive_reads'],c['price_matrix']['consecutive_reads']),(1,2,3))
        self.assertEqual(c['price_matrix']['activity_evidence'],'NEW_CANDLE_VOLUME')
        self.assertEqual(c['price_matrix']['state'],'CONFIRMED')

    def test_04_no_volume_in_new_hour_does_not_confirm(self):
        self.read(17,100,10)
        self.read(32,105,15)
        self.read(47,104,19)
        c=self.read(62,103,0)
        self.assertNotEqual(c['price_matrix']['state'],'CONFIRMED')
        self.assertEqual(c['price_matrix']['consecutive_reads'],2)

    def test_05_stale_or_missing_volume_never_counts_as_proof(self):
        self.read(2,100,10)
        a=self.read(17,105,None)
        b=self.read(32,105,20)
        c=self.read(47,105,20)
        self.assertEqual([x['price_matrix']['consecutive_reads'] for x in (a,b,c)],[0,0,0])
        self.assertFalse(c['price_matrix']['activity_verified'])

    def test_06_volume_correction_downwards_is_not_activity(self):
        self.read(2,100,90)
        first=self.read(17,105,100)
        revision=self.read(32,105,90)
        self.assertEqual(first['price_matrix']['consecutive_reads'],1)
        self.assertEqual(revision['price_matrix']['consecutive_reads'],1)
        self.assertEqual(revision['price_matrix']['activity_evidence'],'VOLUME_REVISION')

    def test_07_carried_price_does_not_count_even_if_volume_changes(self):
        self.read(2,100,10)
        carried=self.read(17,105,15,origin='carried_previous_close')
        self.assertEqual(carried['price_matrix']['consecutive_reads'],0)
        self.assertEqual(carried['price_matrix']['activity_evidence'],'CARRIED_PRICE')

    def test_08_out_of_order_or_too_soon_does_not_write(self):
        self.read(2,100,10)
        self.read(17,105,20)
        previous=KI.Store(self.db).get_price_matrix('XYZ')
        out=self.read(12,106,30)
        close=self.read(18,106,40)
        self.assertEqual(out['status'],'OUT_OF_ORDER')
        self.assertEqual(close['status'],'TOO_SOON')
        self.assertEqual(KI.Store(self.db).get_price_matrix('XYZ'),previous)

    def test_09_legacy_confirmed_without_activity_is_not_validated(self):
        self.read(2,100,10)
        with self.store.transaction() as c:
            row=c.execute("SELECT payload FROM price_matrix WHERE ticker='XYZ'").fetchone()
            import json
            old=json.loads(row[0]);old.update(state='CONFIRMED',consecutive_reads=3,confirmed_at=self.base.isoformat())
            old.pop('activity_verified',None);old.pop('activity_tracking_version',None);old.pop('last_volume',None);old.pop('last_candle_time',None)
            c.execute('UPDATE price_matrix SET payload=? WHERE ticker=?',(KI.json_text(old),'XYZ'))
        no_evidence=self.read(17,105,10)
        self.assertEqual(no_evidence['price_matrix']['consecutive_reads'],0)
        self.assertFalse(no_evidence['price_matrix']['activity_verified'])
        s={**self.snap(17,105,10),'price_matrix':no_evidence['price_matrix']}
        self.assertFalse(KI.two_candle_confirmation(s,self.base+timedelta(minutes=17)))

    def test_10_no_activity_holds_proofs_and_does_not_delete_history(self):
        self.read(2,100,10)
        first=self.read(17,105,20)
        idle=self.read(32,105,20)
        next_read=self.read(47,104,30)
        self.assertEqual(first['price_matrix']['consecutive_reads'],1)
        self.assertEqual(idle['price_matrix']['consecutive_reads'],1)
        self.assertEqual(next_read['price_matrix']['consecutive_reads'],2)
        with self.store.connection() as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM observations').fetchone()[0],4)

    def test_11_proved_event_flows_to_job_once_after_three_activity_steps(self):
        self.store.save_section('tickers',['XYZ'])
        self.read(17,100,10)
        for m,price,volume in ((32,104,20),(47,103,30),(62,103,8)):
            r=self.read(m,price,volume)
            s={**self.snap(m,price,volume),'price_matrix':r['price_matrix']}
            opportunity=KI.record_opportunity(self.store,s,'cycle'+str(m),self.base+timedelta(minutes=m))
            if m<62:
                self.assertEqual(opportunity['state'],'CANDIDATE')
            else:
                self.assertEqual(opportunity['state'],'CONFIRMED')
        selected=KI.reserve_opportunities(self.store,'cycle62',self.base+timedelta(minutes=62))
        self.assertEqual(len(selected),1)
        self.assertTrue(KI.queue_opportunity(self.store,selected[0]['sequence_id'],{},False,self.base+timedelta(minutes=62)))
        self.assertFalse(KI.queue_opportunity(self.store,selected[0]['sequence_id'],{},False,self.base+timedelta(minutes=62)))
        with self.store.connection() as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM analysis_jobs').fetchone()[0],1)

    def test_12_old_job_without_new_activity_proof_filtered_before_api(self):
        self.store.save_section('tickers',['XYZ'])
        now=datetime.now(timezone.utc).replace(second=0,microsecond=0)
        snap=KI.opportunity_test_snapshot(now,ticker='XYZ',price=105)
        matrix={'anchor_price':100.,'anchor_at':(now-timedelta(minutes=45)).isoformat(),
                'last_price':105.,'last_acquired_at':snap['acquired_at'],'state':'CONFIRMED',
                'consecutive_reads':3,'candidate_started_at':(now-timedelta(minutes=30)).isoformat(),
                'change_pct':5.}
        snap['price_matrix']=matrix
        self.assertFalse(KI.two_candle_confirmation(snap,now))
        evidence={'kind':'CONFIRMED_OPPORTUNITY','snapshot':snap}
        with self.store.transaction() as c:
            c.execute('INSERT INTO events VALUES(?,?,?,?,?)',('old', 'XYZ', '1h', snap['acquired_at'], KI.json_text(evidence)))
            c.execute('INSERT INTO analysis_jobs(event_id,state,updated_at) VALUES(?,?,?)',('old','PENDING_CONTEXT',snap['acquired_at']))
            c.execute('INSERT INTO observations(ticker,interval,candle_time,acquired_at,candle_status,payload) VALUES(?,?,?,?,?,?)',
                      ('XYZ','1h',snap['candle_time'],snap['acquired_at'],snap['candle_status'],KI.json_text(snap)))
        self.assertIsNone(KI.claim_analysis(self.store))
        with self.store.connection() as c:
            self.assertEqual(c.execute("SELECT state FROM analysis_jobs WHERE event_id='old'").fetchone()[0],'FILTERED')

    def test_13_missing_legacy_candle_time_is_observed_not_proven(self):
        first=KI.record_price_matrix_read(self.store,{
            'ticker':'XYZ','price':100,'acquired_at':self.base.isoformat()},2.0,15)
        later=KI.record_price_matrix_read(self.store,{
            'ticker':'XYZ','price':105,'acquired_at':(self.base+timedelta(minutes=15)).isoformat()},2.0,15)
        self.assertEqual(first['state'],'BASELINE_CREATED')
        self.assertEqual(later['consecutive_reads'],0)
        self.assertFalse(later['activity_verified'])

    def test_14_confirmed_read_count_does_not_grow_past_three(self):
        self.read(2,100,1)
        for minute,volume in ((17,10),(32,20),(47,30),(62,5),(77,10)):
            matrix=self.read(minute,105,volume)['price_matrix']
        self.assertLessEqual(matrix['consecutive_reads'],3)

if __name__=='__main__':
    unittest.main(verbosity=2)
