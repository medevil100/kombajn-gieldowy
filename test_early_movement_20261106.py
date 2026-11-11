"""Real SQLite early alerts, delivery gates and technical plans. No network."""
import copy
import io
import tempfile
import unittest
from contextlib import ExitStack, redirect_stdout
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import KI
import sl_tp
import test_sl_tp_20261027 as plan_fixtures
import test_analysis_verdict_20261031 as ai_fixtures


class EarlyMovementTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store=KI.Store(Path(self.temp.name)/'early.sqlite3')
        self.base=datetime(2026,11,6,10,0,tzinfo=timezone.utc)
        self.cfg={'price_matrix_enabled':True,'auto_scan_interval':15,'price_threshold_pct':2.,
                  'pipeline_enabled':True,'telegram_enabled':True}
        self.store.save_section('settings',self.cfg)
        self.store.save_section('tickers',['AAA.WA'])
        KI._save_daily_history(self.store,'AAA.WA',[{'session_date':'2026-11-05','status':'CLOSED',
            'open':1.,'high':1.,'low':1.,'close':1.,'volume':1000}],self.base)

    def snap(self,minute,price=1.03,volume=None,ticker='AAA.WA'):
        at=self.base+timedelta(minutes=minute);start=at.replace(minute=0)
        volume=100+minute*10 if volume is None else volume
        return {'ticker':ticker,'interval':'1h','currency':'PLN','acquired_at':at.isoformat(),
                'candle_time':start.isoformat(),'candle_end':(start+timedelta(hours=1)).isoformat(),
                'candle_status':'OPEN','price':price,'volume':volume,'average_volume':100.,'rvol':volume/100.,
                'ohlc':{'open':1.,'high':max(price,1.),'low':min(price,1.),'close':price},
                'previous_closed':{},'indicators':{}}

    def read(self,minute,price=1.03,volume=None):
        s=self.snap(minute,price,volume)
        result=KI.detect_market(self.store,s,self.cfg)
        return {**s,'price_matrix':result['price_matrix']}

    def candidate(self):
        self.read(0,1.)
        return self.read(15)

    def evidence(self):
        with self.store.connection() as c:
            return KI.load_payload(c.execute("SELECT payload FROM events WHERE id LIKE 'early_%'").fetchone()[0])

    def counts(self):
        with self.store.connection() as c:
            return tuple(c.execute('SELECT COUNT(*) FROM '+name).fetchone()[0]
                         for name in ('events','outbox','analysis_jobs','research_requests','signal_confirmations'))

    def test_first_new_activity_queues_one_short_local_alert_without_providers(self):
        s=self.candidate();at=KI.parse_market_time(s['acquired_at'])
        with patch.object(KI,'service_http',side_effect=AssertionError('network')):
            self.assertTrue(KI.queue_early_movement(self.store,s,at))
        self.assertEqual(self.counts(),(1,1,0,0,0))
        with self.store.connection() as c:
            row=c.execute('SELECT * FROM outbox').fetchone()
        self.assertEqual(row['kind'],'EARLY_MOVEMENT')
        self.assertEqual(row['status'],'PENDING')
        self.assertIn('WSTĘPNY WZROST',row['message'])
        self.assertIn('1/3',row['message'])
        self.assertNotIn('POTWIERDZONY',row['message'])
        self.assertLess(len(row['message']),550)
        self.assertIsNotNone(KI.claim_delivery(self.store,now=at))

    def test_restart_and_new_crossing_cannot_duplicate_session_direction(self):
        s=self.candidate();at=KI.parse_market_time(s['acquired_at'])
        self.assertTrue(KI.queue_early_movement(self.store,s,at))
        restarted=KI.Store(self.store.path)
        self.assertFalse(KI.queue_early_movement(restarted,s,at))
        self.read(30,1.)
        s=self.read(45)
        self.assertFalse(KI.queue_early_movement(restarted,s,KI.parse_market_time(s['acquired_at'])))
        self.assertEqual(self.counts()[:3],(1,1,0))

    def test_opposite_direction_has_one_separate_alert(self):
        s=self.candidate();KI.queue_early_movement(self.store,s,KI.parse_market_time(s['acquired_at']))
        self.read(30,1.)
        s=self.read(45,.97)
        self.assertTrue(KI.queue_early_movement(self.store,s,KI.parse_market_time(s['acquired_at'])))
        self.assertEqual(self.counts()[:3],(2,2,0))
        with self.store.connection() as c:
            messages=[r[0] for r in c.execute('SELECT message FROM outbox')]
        self.assertTrue(any('WSTĘPNY SPADEK' in m for m in messages))

    def test_direct_reversal_requires_own_three_proofs_and_early_alert(self):
        self.candidate();self.read(30)
        s=self.read(45,.97);at=self.base+timedelta(minutes=45)
        self.assertEqual(s['price_matrix']['consecutive_reads'],1)
        self.assertFalse(KI.two_candle_confirmation(s,at))
        self.assertTrue(KI.queue_early_movement(self.store,s,at))

    def test_scanner_cycle_enqueues_before_any_quote_research_or_ai_fetch(self):
        self.read(0,1.);s=self.snap(15);at=self.base+timedelta(minutes=15)
        class Clock(datetime):
            @classmethod
            def now(cls,tz=None):return at if tz else at.replace(tzinfo=None)
        with ExitStack() as stack:
            stack.enter_context(patch.object(KI,'datetime',Clock))
            stack.enter_context(patch.object(KI,'fetch_automatic_snapshot',return_value=s))
            stack.enter_context(patch.object(KI,'fetch_opportunity_spread',side_effect=AssertionError('quote fetch')))
            stack.enter_context(patch.object(KI,'service_http',side_effect=AssertionError('provider')))
            for name in ('daily_report_send','us_report_send','portfolio_check_alerts','maintain_signal_history'):
                stack.enter_context(patch.object(KI,name))
            with redirect_stdout(io.StringIO()):result=KI.run_market_cycle(self.store)
        self.assertEqual(result['status'],'OK')
        self.assertTrue(result['results'][0]['early_alert_queued'])
        self.assertEqual(self.counts(),(1,1,0,0,0))

    def test_usa_ticker_uses_same_alert_rules_with_its_market_session(self):
        self.base=datetime(2026,11,6,15,0,tzinfo=timezone.utc)
        self.store.save_section('tickers',['XYZ'])
        KI._save_daily_history(self.store,'XYZ',[{'session_date':'2026-11-05','status':'CLOSED',
            'open':1.,'high':1.,'low':1.,'close':1.,'volume':1000}],self.base)
        for minute,price in ((0,1.),(15,1.03)):
            s=self.snap(minute,price,ticker='XYZ');s['currency']='USD'
            result=KI.detect_market(self.store,s,self.cfg)
        s={**s,'price_matrix':result['price_matrix']};at=self.base+timedelta(minutes=15)
        self.assertTrue(KI.queue_early_movement(self.store,s,at))
        self.assertIsNotNone(KI.claim_delivery(self.store,now=at))

    def test_no_startup_or_unchanged_volume_alert(self):
        s=self.read(0)
        self.assertFalse(KI.queue_early_movement(self.store,s,self.base))
        s=self.read(15,1.05,100)
        self.assertFalse(KI.queue_early_movement(self.store,s,self.base+timedelta(minutes=15)))
        self.assertEqual(self.counts(),(0,0,0,0,0))

    def test_second_read_is_not_backfilled_after_install(self):
        self.candidate();s=self.read(30)
        self.assertEqual(s['price_matrix']['consecutive_reads'],2)
        self.assertFalse(KI.queue_early_movement(self.store,s,self.base+timedelta(minutes=30)))

    def test_disabled_switches_and_removed_ticker_never_queue(self):
        s=self.candidate();at=KI.parse_market_time(s['acquired_at'])
        for key in ('pipeline_enabled','telegram_enabled'):
            self.store.save_section('settings',{**self.cfg,key:False})
            self.assertFalse(KI.queue_early_movement(self.store,s,at))
        self.store.save_section('settings',self.cfg);self.store.save_section('tickers',[])
        self.assertFalse(KI.queue_early_movement(self.store,s,at))

    def test_bad_reference_stale_price_carried_price_currency_and_ohlc_rejected(self):
        s=self.candidate();at=KI.parse_market_time(s['acquired_at'])
        changes=[{'latest_price_origin':'carried_previous_close'}, {'currency':'USD'},
                 {'ohlc':{'open':1.,'high':1.,'low':1.,'close':1.03}},
                 {'price_matrix':{**s['price_matrix'],'reference_status':'MISSING_PREVIOUS_SESSION'}},
                 {'price_matrix':{**s['price_matrix'],'read_status':'TOO_SOON'}},
                 {'price_matrix':{**s['price_matrix'],'activity_evidence':'NO_NEW_ACTIVITY'}}]
        for change in changes:
            self.assertFalse(KI.queue_early_movement(self.store,{**s,**change},at),change)
        self.assertFalse(KI.queue_early_movement(self.store,s,at+timedelta(minutes=16)))
        self.assertEqual(self.counts(),(0,0,0,0,0))

    def test_first_proof_does_not_bypass_three_read_confirmation(self):
        s=self.candidate();KI.queue_early_movement(self.store,s,self.base+timedelta(minutes=15))
        self.assertFalse(KI.two_candle_confirmation(s,self.base+timedelta(minutes=15)))
        self.read(30);s=self.read(45)
        self.assertTrue(KI.two_candle_confirmation(s,self.base+timedelta(minutes=45)))
        self.assertEqual(self.counts()[-1],1)
        self.assertFalse(KI.queue_early_movement(self.store,s,self.base+timedelta(minutes=45)))

    def test_pending_early_alert_dropped_on_confirmation_or_reversal(self):
        for final_price in (1.03,.97):
            with self.subTest(price=final_price):
                with self.store.transaction() as c:
                    for table in ('outbox','events','observations','price_matrix','baselines','signal_technical_context','signal_confirmations'):
                        c.execute('DELETE FROM '+table)
                s=self.candidate();KI.queue_early_movement(self.store,s,self.base+timedelta(minutes=15))
                self.read(30);self.read(45,final_price)
                self.assertIsNone(KI.claim_delivery(self.store,now=self.base+timedelta(minutes=45)))
                with self.store.connection() as c:
                    self.assertEqual(c.execute('SELECT status FROM outbox').fetchone()[0],'FILTERED')

    def test_delivery_rechecks_latest_reference_and_watchlist(self):
        s=self.candidate();at=KI.parse_market_time(s['acquired_at'])
        KI.queue_early_movement(self.store,s,at);ev=self.evidence()
        self.assertTrue(KI.early_delivery_valid(self.store,ev,at))
        self.store.save_section('tickers',[])
        self.assertFalse(KI.early_delivery_valid(self.store,ev,at))
        self.store.save_section('tickers',['AAA.WA'])
        latest=copy.deepcopy(s);latest['price_matrix']['anchor_at']='2026-11-05T16:05:00Z'
        with self.store.transaction() as c:
            c.execute('UPDATE observations SET payload=? WHERE id=(SELECT MAX(id) FROM observations)',(KI.json_text(latest),))
        self.assertFalse(KI.early_delivery_valid(self.store,ev,at))

    def test_uncertain_delivery_is_never_automatically_replayed(self):
        s=self.candidate();at=KI.parse_market_time(s['acquired_at'])
        KI.queue_early_movement(self.store,s,at);KI.claim_delivery(self.store,now=at)
        KI.recover_service_jobs(self.store,'telegram')
        with self.store.connection() as c:
            self.assertEqual(c.execute('SELECT status FROM outbox').fetchone()[0],'UNCERTAIN')
        self.assertIsNone(KI.claim_delivery(self.store,now=at))
        self.assertFalse(KI.queue_early_movement(self.store,s,at))

    def test_telegram_worker_delivers_early_without_ai_job_using_mock_transport(self):
        s=self.candidate();at=KI.parse_market_time(s['acquired_at'])
        KI.queue_early_movement(self.store,s,at)
        class Clock(datetime):
            @classmethod
            def now(cls,tz=None):return at if tz else at.replace(tzinfo=None)
        reply={'ok':True,'result':{'message_id':123,'chat':{'id':456}}}
        with patch.object(KI,'datetime',Clock), patch.object(KI,'service_http',return_value=reply) as transport:
            self.assertTrue(KI.process_delivery_once(self.store,{'TELEGRAM_BOT_TOKEN':'fake','TELEGRAM_CHAT_ID':'456'}))
            transport.assert_called_once()
            self.assertIn('WSTĘPNY WZROST',transport.call_args.kwargs['payload']['text'])
        with self.store.connection() as c:
            self.assertEqual(c.execute('SELECT status FROM outbox').fetchone()[0],'DELIVERED')
            self.assertEqual(c.execute('SELECT message_id FROM delivery_receipts').fetchone()[0],123)
        self.assertEqual(self.counts()[2:4],(0,0))


class InformationalQuotesTests(unittest.TestCase):
    def test_missing_or_wide_quotes_never_create_an_additional_ai_question(self):
        ev,ctx,_=ai_fixtures.AutonomousReviewTests().sample()
        base=KI.automatic_ai_preflight(ev,ctx)
        for quotes in ({},{'bid':1.,'ask':200.},{'bid':200.,'ask':1.}):
            changed=copy.deepcopy(ev);changed['snapshot']['spread']=quotes
            decision=KI.automatic_ai_preflight(changed,ctx)
            for key in ('allowed','questions','skip_reasons'):
                self.assertEqual(decision[key],base[key])

    def test_wide_unknown_inverted_and_missing_quotes_do_not_change_technical_plan(self):
        s,at=plan_fixtures.TradePlanTests().sample();base=sl_tp.build_plan(s,3,at)
        for quotes in ({},{'bid':1.,'ask':20.},{'bid':20.,'ask':1.},
                       {'bid':9.,'ask':15.,'freshness_confirmed':True,'quote_time':at.isoformat()}):
            plan=sl_tp.build_plan({**s,'spread':quotes},3,at)
            self.assertEqual(plan['status'],'INDICATIVE')
            for key in ('entry','sl','tp1','tp2','rr1','rr2'):
                self.assertEqual(plan[key],base[key])
            self.assertFalse(plan['execution_confirmed'])

    def test_unverified_spread_is_information_not_proof_of_high_risk(self):
        s={'acquired_at':'2026-11-06T10:15:00Z','price':10.,'ohlc':{'high':10.,'low':10.},
           'spread':{'bid':1.,'ask':20.,'spread_pct':0.,'freshness_confirmed':True}}
        risk=KI.opportunity_risk(s)
        self.assertFalse(risk['reasons']);self.assertTrue(risk['informational'])
        self.assertGreater(risk['spread_pct'],100)
        s['spread']['quote_time']=s['acquired_at']
        self.assertIn('Spread bid/ask ≥ 2%',KI.opportunity_risk(s)['reasons'])
        s['spread']['quote_time']='2026-11-06T10:00:00Z'
        self.assertFalse(KI.opportunity_risk(s)['reasons'])


if __name__=='__main__':unittest.main()
