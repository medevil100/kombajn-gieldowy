import copy
import tempfile
import unittest
from datetime import datetime,timedelta,timezone
from pathlib import Path
from contextlib import ExitStack
from unittest.mock import patch
import KI
import technical_radar as radar


class TechnicalRadarTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.store=KI.Store(Path(self.temp.name)/'test.sqlite3')
        self.now=datetime(2026,11,20,16,tzinfo=timezone.utc)
        self.rows=[]
        for i in range(60):
            at=self.now-timedelta(days=61-i)
            self.rows.append({'time':at.isoformat(),'end':(at+timedelta(hours=1)).isoformat(),
                'open':9.,'high':10.,'low':8.,'close':9.,'volume':100.,'status':'CLOSED'})
        self.snap={'ticker':'AAA','price':11.,'currency':'USD','acquired_at':self.now.isoformat(),
            'volume':200.,'candle_status':'OPEN','indicators':{'ma_fast':10.,'ma_slow':9.,'last_macd_hist':.1,'rsi':65.},
            'previous_closed':{'status':'CLOSED','end':self.now.isoformat(),'rvol':2.},
            'trend_context':{'horizons':{k:{'direction':'UP'} for k in ('session','short','medium','long')}}}
        self.store.save_section('tickers',['AAA'])

    def test_breakout_without_higher_resistance_is_eligible_not_rejected(self):
        result=radar.evaluate(self.snap,self.rows)
        self.assertTrue(result['breakout']);self.assertTrue(result['large_eligible'])
        self.assertFalse(result['full_52w'])
        self.assertIn('dostępnej historii',' '.join(result['reasons']))

    def test_same_data_does_not_accumulate_score_and_old_read_cannot_replace(self):
        with patch('large_movement.daily_rows',return_value=self.rows):
            first=radar.record(KI,self.store,self.snap)
            self.assertIsNone(radar.record(KI,self.store,self.snap))
            later={**self.snap,'acquired_at':(self.now+timedelta(minutes=15)).isoformat()}
            second=radar.record(KI,self.store,later)
            self.assertEqual(first['growth_score'],second['growth_score'])
            self.assertIsNone(radar.record(KI,self.store,self.snap))

    def test_top_exit_keeps_durable_watch_and_tracks_weakening(self):
        with patch('large_movement.daily_rows',return_value=self.rows):
            radar.record(KI,self.store,self.snap)
            radar.finish_cycle(KI,self.store,self.now.isoformat())
            weak=copy.deepcopy(self.snap);weak.update(price=8.5,acquired_at=(self.now+timedelta(minutes=15)).isoformat())
            weak['trend_context']['horizons']={k:{'direction':'DOWN'} for k in ('session','short','medium','long')}
            weak['indicators']['last_macd_hist']=-.1
            radar.record(KI,self.store,weak)
            radar.finish_cycle(KI,self.store,weak['acquired_at'])
        with self.store.connection() as c:
            row=c.execute('SELECT * FROM technical_watch').fetchone()
            self.assertEqual(row['status'],'WEAKENED')
            self.assertEqual(row['opened_at'],self.now.isoformat())
            self.assertEqual(row['updated_at'],weak['acquired_at'])

    def test_saved_top_and_large_case_are_followed_with_radar_off(self):
        self.store.update_settings({'technical_radar_enabled':False})
        with self.store.transaction() as c:
            c.execute('CREATE TABLE ki_top5_follow(ticker TEXT PRIMARY KEY,status TEXT,first_at TEXT,last_at TEXT)')
            c.execute("INSERT INTO ki_top5_follow VALUES('TOP.WA','FOLLOWING','a','a')")
            c.execute("INSERT INTO ki_top5_follow VALUES('OLD.WA','CLOSED','a','a')")
            for ticker,status in (('LARGE.WA','REVIEW_FAILED'),('BASIS.WA','BASIS_REVIEW')):
                c.execute('''INSERT INTO large_movement_cases
                    (ticker,status,opened_at,updated_at,market_at,price,currency,result)
                    VALUES(?,?,?,?,?,?,?,?)''',
                    (ticker,status,self.now.isoformat(),self.now.isoformat(),self.now.isoformat(),1.,'PLN','{}'))
        self.assertFalse(radar.enabled(self.store.load_section('settings',{})))
        followed=set(radar.monitored_tickers(self.store))
        self.assertTrue({'TOP.WA','LARGE.WA','BASIS.WA'}<=followed)
        self.assertNotIn('OLD.WA',followed)

    def test_invalid_basis_scores_zero_and_blocks_promotion(self):
        result=radar.evaluate({**self.snap,'price_basis':{'blocked':True}},self.rows)
        self.assertEqual(result['growth_score'],0)
        self.assertFalse(result['large_eligible'])

    def test_mode_with_pipeline_off_blocks_paid_jobs_but_allows_telegram(self):
        self.store.update_settings({'technical_radar_enabled':True,'telegram_enabled':True,'pipeline_enabled':False})
        with patch.object(KI,'claim_analysis',side_effect=AssertionError('paid work')):
            self.assertFalse(KI.process_analysis_once(self.store,{}))
        self.assertFalse(KI.process_issuer_watch_once(self.store,{}))
        self.assertTrue(KI.telegram_delivery_active(self.store))

    def test_digest_once_and_delivery_does_not_require_paid_pipeline(self):
        self.store.update_settings({'technical_radar_enabled':True,'telegram_enabled':True,'pipeline_enabled':False})
        with patch('large_movement.daily_rows',return_value=self.rows):
            radar.record(KI,self.store,self.snap)
            radar.finish_cycle(KI,self.store,self.now.isoformat())
            radar.finish_cycle(KI,self.store,self.now.isoformat())
        with self.store.connection() as c:
            self.assertEqual(c.execute('SELECT count(*) FROM outbox').fetchone()[0],1)
        item=KI.claim_delivery(self.store,now=self.now)
        self.assertEqual(item['kind'],'TECHNICAL_DIGEST')
        self.assertIsNone(KI.claim_delivery(self.store,now=self.now))

    def test_panel_reads_only_and_renders_saved_watch(self):
        with patch('large_movement.daily_rows',return_value=self.rows):
            radar.record(KI,self.store,self.snap);radar.finish_cycle(KI,self.store,self.now.isoformat())
        with self.store.connection() as c:before=list(c.iterdump())
        from streamlit.testing.v1 import AppTest
        app=AppTest.from_string('import KI,technical_radar\nfrom pathlib import Path\ntechnical_radar.render(KI.Store(Path('+repr(str(self.store.path))+')))').run(timeout=30)
        self.assertEqual(len(app.exception),0)
        with self.store.connection() as c:self.assertEqual(before,list(c.iterdump()))

    def test_corrupt_ohlc_does_not_promote(self):
        value=radar.evaluate({**self.snap,'ohlc':{'open':9.,'high':10.,'low':8.,'close':11.}},self.rows)
        self.assertFalse(value['valid']);self.assertEqual(value['growth_score'],0)

    def test_confirmation_waits_for_later_daily_close_and_keeps_frozen_level(self):
        state=radar.evaluate(self.snap,self.rows)
        saved={'entry_at':state['as_of'],'breakout_level':10.}
        self.assertEqual(radar.confirmation(saved,state,[])['status'],'DETECTED')
        later={**state,'as_of':(self.now+timedelta(days=3)).isoformat()}
        rows=[{'close':10.5,'closed_at':(self.now+timedelta(days=1)).isoformat(),'session_date':'2026-11-21'}]
        self.assertEqual(radar.confirmation(saved,later,rows)['status'],'CONFIRMED')
        raised=copy.deepcopy(self.rows);raised[-1]['high']=12.
        result=radar.evaluate(self.snap,raised,saved)
        self.assertTrue(result['breakout']);self.assertEqual(result['first_resistance'],10.)

    def test_scanner_records_technical_state_without_scheduling_paid_work(self):
        self.store.update_settings({'technical_radar_enabled':True,'pipeline_enabled':True,'telegram_enabled':False})
        with ExitStack() as stack:
            stack.enter_context(patch.object(KI,'fetch_automatic_snapshot',return_value=self.snap))
            stack.enter_context(patch.object(KI,'attach_historical_baseline'))
            stack.enter_context(patch.object(KI.market_intelligence,'attach'))
            stack.enter_context(patch.object(KI,'detect_market',return_value={'status':'CONFIRMED','price_matrix':{},'reasons':[]}))
            stack.enter_context(patch('large_movement.daily_rows',return_value=self.rows))
            for name in ('portfolio_check_alerts','daily_report_send','us_report_send','maintain_signal_history'):
                stack.enter_context(patch.object(KI,name))
            stack.enter_context(patch.object(KI,'reserve_opportunities',side_effect=AssertionError('paid scheduling')))
            scheduled=stack.enter_context(patch('radar_ai.schedule',return_value=0))
            stack.enter_context(patch.object(KI,'service_http',side_effect=AssertionError('provider')))
            result=KI.run_market_cycle(self.store)
        self.assertEqual(result['status'],'OK')
        scheduled.assert_called_once()
        with self.store.connection() as c:
            self.assertEqual(c.execute('SELECT count(*) FROM technical_radar').fetchone()[0],1)
            self.assertEqual(c.execute('SELECT count(*) FROM analysis_jobs').fetchone()[0],0)

    def test_promotion_then_activity_dip_retains_large_until_price_fails(self):
        with patch('large_movement.daily_rows',return_value=self.rows):
            radar.record(KI,self.store,self.snap);radar.finish_cycle(KI,self.store,self.now.isoformat())
            def status():
                with self.store.connection() as c:return c.execute('SELECT status FROM technical_watch').fetchone()[0]
            self.assertEqual(status(),'TRACKING')
            monday=self.now+timedelta(days=3)
            closed={'session_date':'2026-11-20','closed_at':(self.now+timedelta(hours=5)).isoformat(),'close':10.8}
            following=copy.deepcopy(self.snap);following['acquired_at']=monday.isoformat()
            following['previous_closed']['end']=monday.isoformat()
            with patch.object(KI,'load_daily_candles',return_value=[closed]):
                radar.record(KI,self.store,following);radar.finish_cycle(KI,self.store,monday.isoformat())
                self.assertEqual(status(),'LARGE')
                following['acquired_at']=(monday+timedelta(minutes=15)).isoformat()
                following['previous_closed']['rvol']=.5
                following['trend_context']['horizons']['session']['direction']='MIXED'
                following['indicators']['ma_slow']=10.5
                radar.record(KI,self.store,following);radar.finish_cycle(KI,self.store,following['acquired_at'])
                self.assertEqual(status(),'LARGE')
                following.update(price=9.9,acquired_at=(monday+timedelta(minutes=30)).isoformat())
                radar.record(KI,self.store,following);radar.finish_cycle(KI,self.store,following['acquired_at'])
                self.assertEqual(status(),'WEAKENED')

    def test_manual_close_survives_legacy_case_and_next_cycle(self):
        with patch('large_movement.daily_rows',return_value=self.rows):
            radar.record(KI,self.store,self.snap);radar.finish_cycle(KI,self.store,self.now.isoformat())
            radar.close_watch(self.store,'AAA',self.now)
            self.assertNotIn('AAA',radar.monitored_tickers(self.store))
            radar.finish_cycle(KI,self.store,self.now.isoformat())
        with self.store.connection() as c:self.assertEqual(c.execute('SELECT status FROM technical_watch').fetchone()[0],'CLOSED')

    def test_split_after_entry_blocks_old_levels_even_outside_recent_action_window(self):
        with patch('large_movement.daily_rows',return_value=self.rows):
            radar.record(KI,self.store,self.snap);radar.finish_cycle(KI,self.store,self.now.isoformat())
            following={**self.snap,'acquired_at':(self.now+timedelta(days=14)).isoformat(),
                       'corporate_actions':[{'effective_at':(self.now+timedelta(days=1)).isoformat(),'kind':'REVERSE_SPLIT'}]}
            result=radar.record(KI,self.store,following)
            self.assertTrue(result['blocked']);self.assertEqual(result['growth_score'],0)
            radar.finish_cycle(KI,self.store,following['acquired_at'])
        with self.store.connection() as c:self.assertEqual(c.execute('SELECT status FROM technical_watch').fetchone()[0],'BASIS_REVIEW')

    def test_failed_legacy_ai_is_preserved_but_does_not_block_technical_tracking(self):
        import json
        original={'as_of':'2026-11-13T15:00:00+00:00','reference_price':3.5,'invalidation':None,'why':['Nie otrzymano poprawnej oceny AI.']}
        with self.store.transaction() as c:
            c.execute('INSERT INTO large_movement_cases(ticker,status,opened_at,updated_at,market_at,price,currency,result) VALUES(?,?,?,?,?,?,?,?)',
                      ('AAA','REVIEW_FAILED',original['as_of'],original['as_of'],original['as_of'],3.5,'USD',json.dumps(original)))
        with patch('large_movement.daily_rows',return_value=self.rows):
            radar.record(KI,self.store,self.snap);radar.finish_cycle(KI,self.store,self.now.isoformat())
        with self.store.connection() as c:
            row=c.execute('SELECT * FROM technical_watch').fetchone();saved=json.loads(row['payload'])
            self.assertEqual(saved['legacy']['assessment_at'],original['as_of'])
            self.assertEqual(saved['entry_price'],11.)
            self.assertEqual(row['status'],'TRACKING')
            self.assertEqual(json.loads(c.execute('SELECT result FROM large_movement_cases').fetchone()[0]),original)

    def test_52w_maximum_requires_every_expected_exchange_session(self):
        from session_context import bounds
        at=self.now;coverage=radar.history_coverage('AAA',at,[])
        rows=[]
        for day in sorted(radar.session_dates('XNYS',coverage['from'],coverage['to'])):
            opening,closing=bounds('XNYS',day)
            rows.append({'time':day+'T00:00:00-05:00','end':closing.isoformat(),'open':9.,'high':10.,'low':8.,'close':9.,'volume':100.,'status':'CLOSED'})
        self.assertTrue(radar.evaluate(self.snap,rows)['full_52w'])
        rows.pop(len(rows)//2)
        result=radar.evaluate(self.snap,rows)
        self.assertFalse(result['full_52w']);self.assertEqual(result['history_coverage']['missing_sessions'],1)


if __name__=='__main__':unittest.main()
