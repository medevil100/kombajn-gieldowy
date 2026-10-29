"""Daily-reference recovery: real SQLite, synthetic market data, no network."""
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
import KI


class DailyReadinessTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store=KI.Store(Path(self.tmp.name)/'daily.sqlite3')
        self.now=datetime(2026,10,29,8,tzinfo=timezone.utc)

    def seed(self,day='2026-10-28',close=100.,now=None):
        KI._save_daily_history(self.store,'AAA.WA',[{'session_date':day,'status':'CLOSED',
            'open':close,'high':close,'low':close,'close':close,'volume':100}],now or self.now)

    def snap(self,minute=0,price=103.):
        now=self.now+timedelta(minutes=minute)
        candle=now.replace(minute=0)
        return {'ticker':'AAA.WA','interval':'1h','price':price,'acquired_at':now.isoformat(),
                'candle_time':candle.isoformat(),'candle_end':(candle+timedelta(hours=1)).isoformat(),
                'candle_status':'OPEN','volume':1000+minute,'rvol':2.,'average_volume':500.,
                'ohlc':{'open':100.,'high':110.,'low':99.,'close':price},
                'previous_closed':{'time':(candle-timedelta(hours=1)).isoformat(),
                    'end':candle.isoformat(),'status':'CLOSED','open':100.,'high':110.,'low':99.,'close':101.,'volume':1000},
                'indicators':{'ma_fast':101.,'last_macd_hist':1.,'plus_di':20.,'minus_di':10.,'adx':25.}}

    def test_incomplete_success_retries_only_after_fifteen_minutes(self):
        self.seed('2026-10-27')
        self.assertFalse(KI.daily_history_refresh_due(self.store,'AAA.WA',self.now+timedelta(minutes=14)))
        self.assertTrue(KI.daily_history_refresh_due(self.store,'AAA.WA',self.now+timedelta(minutes=15)))
        self.seed('2026-10-27',now=self.now+timedelta(minutes=15))
        self.assertFalse(KI.daily_history_refresh_due(self.store,'AAA.WA',self.now+timedelta(minutes=16)))
        self.assertTrue(KI.daily_history_refresh_due(self.store,'AAA.WA',self.now+timedelta(minutes=30)))

    def test_partial_daily_response_does_not_cause_request_storm(self):
        self.seed('2026-10-27')
        calls=[]
        acquired=self.now+timedelta(minutes=15)
        def fetch(ticker,interval):
            calls.append(interval)
            if interval=='1d':
                return {'acquired_at':acquired.isoformat(),'daily_history':[
                    {'session_date':'2026-10-27','status':'CLOSED','open':100.,'high':100.,'low':100.,'close':100.,'volume':100}],
                    'rejected_source_rows':[{'time':'2026-10-28T00:00:00+01:00','reason':'Incomplete OHLCV'}]}
            return self.snap(15)
        with patch.object(KI,'fetch_market',side_effect=fetch):
            KI.fetch_automatic_snapshot(self.store,'AAA.WA',acquired)
            KI.fetch_automatic_snapshot(self.store,'AAA.WA',acquired+timedelta(minutes=1))
        self.assertEqual(calls,['1d','1h','1h'])

    def test_complete_history_stops_retries_and_survives_restart(self):
        self.seed()
        self.assertFalse(KI.daily_history_refresh_due(KI.Store(self.store.path),'AAA.WA',self.now+timedelta(hours=2)))

    def test_missing_reference_blocks_matrix_rank_alert_and_preflight(self):
        self.seed('2026-10-27')
        for minute in (0,15,30,45):
            snap=self.snap(minute)
            row=KI.record_price_matrix_read(self.store,snap,2.,15)
            self.assertEqual(row['state'],'MISSING_DAILY_REFERENCE')
            self.assertEqual(row['consecutive_reads'],0)
            snap['price_matrix']=row
            self.assertFalse(KI.two_candle_candidate(snap,KI.parse_market_time(snap['acquired_at'])))
            self.assertFalse(KI.should_alert(snap,None,{'AAA.WA'},KI.parse_market_time(snap['acquired_at']))[0])
            decision=KI.automatic_ai_preflight({'snapshot':snap},{})
            self.assertFalse(decision['allowed'])
            self.assertTrue(any('baza' in x for x in decision['skip_reasons']))

    def test_late_reference_resets_proofs_and_needs_three_new_activities(self):
        self.seed('2026-10-27')
        KI.record_price_matrix_read(self.store,self.snap(),2.,15)
        self.seed(close=101.,now=self.now+timedelta(minutes=15))
        first=KI.record_price_matrix_read(self.store,self.snap(15,110.),2.,15)
        self.assertEqual(first['state'],'BASELINE_CREATED')
        self.assertEqual(first['anchor_price'],101.)
        self.assertEqual(first['consecutive_reads'],0)
        rows=[KI.record_price_matrix_read(self.store,self.snap(m,110.),2.,15) for m in (30,45,60)]
        self.assertEqual([r['consecutive_reads'] for r in rows],[1,2,3])
        self.assertEqual(rows[-1]['state'],'CONFIRMED')
        with self.store.connection() as c:
            self.assertEqual(c.execute('select count(*) from analysis_jobs').fetchone()[0],0)
            self.assertEqual(c.execute('select count(*) from outbox').fetchone()[0],0)

    def test_existing_wrong_anchor_changes_even_within_same_session(self):
        self.seed()
        first=KI.record_price_matrix_read(self.store,self.snap(),2.,15)
        for m in (15,30,45):KI.record_price_matrix_read(self.store,self.snap(m),2.,15)
        self.seed(close=102.,now=self.now+timedelta(minutes=46))
        row=KI.record_price_matrix_read(KI.Store(self.store.path),self.snap(46),2.,15)
        self.assertEqual(row['anchor_price'],102.)
        self.assertEqual(row['consecutive_reads'],0)
        self.assertEqual(row['state'],'BASELINE_CREATED')
        self.assertAlmostEqual(row['change_pct'],(103/102-1)*100)

    def test_restored_legacy_wrong_day_anchor_is_rebased(self):
        self.seed()
        row=KI.record_price_matrix_read(self.store,self.snap(),2.,15)
        row.update(anchor_price=90.,anchor_at='2026-10-27T17:00:00+01:00',reference_session='2026-10-27',state='CONFIRMED',consecutive_reads=3,activity_verified=True)
        row.pop('reference_status',None)
        with self.store.transaction() as c:c.execute('update price_matrix set payload=?',(json.dumps(row),))
        new=KI.record_price_matrix_read(self.store,self.snap(15),2.,15)
        self.assertEqual(new['anchor_price'],100.)
        self.assertEqual(new['consecutive_reads'],0)

    def test_pending_wrong_reference_is_filtered_without_any_provider(self):
        self.seed()
        snap=self.snap()
        snap['price_matrix']={'reference_session':'2026-10-27','anchor_price':90.,'anchor_at':'2026-10-27T17:00:00+01:00'}
        evidence={'kind':'CONFIRMED_OPPORTUNITY','snapshot':snap}
        with self.store.transaction() as c:
            c.execute('insert into events values(?,?,?,?,?)',('e','AAA.WA','1h',KI.utc_now(),json.dumps(evidence)))
            c.execute('insert into analysis_jobs(event_id,state,updated_at) values(?,?,?)',('e','PENDING_CONTEXT',KI.utc_now()))
        with patch.object(KI,'submit_event_research',side_effect=AssertionError('paid call')),patch.object(KI,'analyze_event',side_effect=AssertionError('paid call')):
            self.assertFalse(KI.process_analysis_once(self.store,{},'e'))
            self.assertFalse(KI.process_analysis_once(self.store,{},'e'))
        with self.store.connection() as c:
            self.assertEqual(c.execute('select state from analysis_jobs').fetchone()[0],'FILTERED')
            self.assertEqual(c.execute('select count(*) from research_requests').fetchone()[0],0)

    def test_worker_blocks_changed_close_before_research_or_ai(self):
        self.seed(close=102.)
        for state in ('PENDING_CONTEXT','PENDING_AI'):
            event='changed-'+state
            snap=self.snap()
            snap['price_matrix']={'reference_session':'2026-10-28','anchor_price':100.,'anchor_at':'2026-10-28T17:00:00+01:00'}
            evidence={'kind':'CONFIRMED_OPPORTUNITY','snapshot':snap}
            with self.store.transaction() as c:
                c.execute('insert into events values(?,?,?,?,?)',(event,'AAA.WA','1h',KI.utc_now(),json.dumps(evidence)))
                c.execute('insert into analysis_jobs(event_id,state,updated_at) values(?,?,?)',(event,state,KI.utc_now()))
            with patch.object(KI,'opportunity_delivery_valid',return_value=True),patch.object(KI,'submit_event_research',side_effect=AssertionError('paid call')),patch.object(KI,'analyze_event',side_effect=AssertionError('paid call')):
                self.assertTrue(KI.process_analysis_once(self.store,{},event))
            with self.store.connection() as c:
                self.assertEqual(c.execute('select state from analysis_jobs where event_id=?',(event,)).fetchone()[0],'FILTERED')
                self.assertEqual(c.execute('select count(*) from research_requests').fetchone()[0],0)

    def test_reference_rebase_cannot_create_second_paid_identity_same_day(self):
        snap=self.snap()
        snap['price_matrix']={'reference_rebased':True}
        old={'snapshot':self.snap()}
        with self.store.transaction() as c:
            c.execute('insert into events values(?,?,?,?,?)',('paid','AAA.WA','1h',self.now.isoformat(),json.dumps(old)))
            KI.reserve_research(c,'paid','Verified issuer',self.now.isoformat())
            self.assertTrue(KI.rebase_research_already_reserved(c,snap,'new-identity'))
            self.assertFalse(KI.rebase_research_already_reserved(c,snap,'paid'))
            snap['acquired_at']=(self.now+timedelta(days=1)).isoformat()
            self.assertFalse(KI.rebase_research_already_reserved(c,snap,'new-identity'))
            self.assertEqual(c.execute('select count(*) from research_requests').fetchone()[0],1)

    def test_weekend_and_exchange_timezone_are_explicit(self):
        self.assertEqual(KI.required_daily_session('AAA.WA','2026-10-26T08:00:00Z'),'2026-10-23')
        self.assertEqual(KI.required_daily_session('AAA','2026-10-29T01:00:00Z'),'2026-10-27')
        self.assertEqual(KI.required_daily_session('AAA.WA','2026-10-29T08:00:00Z'),'2026-10-28')

    def test_old_hourly_candle_still_cannot_enter_ranking(self):
        self.seed();snap=self.snap()
        snap['candle_time']='2026-10-28T08:00:00Z';snap['candle_end']='2026-10-28T09:00:00Z'
        snap['price_matrix']={'reference_session':'2026-10-28','anchor_price':100.,'state':'CONFIRMED','activity_verified':True}
        self.assertFalse(KI.two_candle_candidate(snap,self.now))


if __name__=='__main__':unittest.main()
