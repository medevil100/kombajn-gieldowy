"""Corporate-action regression and horizon/independent-research integration, no network."""
import copy
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd
import KI
import market_intelligence as facts
import issuer_watch as watch
import company_orchestrator
import ki_assistant
import corporate_feed

NOW=datetime(2026,11,13,15,0,tzinfo=timezone.utc)


def action(ratio=.05):
    return {'kind':'REVERSE_SPLIT' if ratio<1 else 'SPLIT','effective_at':'2026-11-13T00:00:00-05:00',
            'new_per_old':ratio,'observed_at':NOW.isoformat(),'source':'Yahoo Finance actions'}


def snap():
    s=KI.opportunity_test_snapshot(NOW,'COSM',3.82)
    s.update(company_name='Cosmos Health Inc.',company_website='https://cosmoshealthinc.com',currency='USD',
             corporate_actions=[action()],chart_history=[{'time':'2026-11-12T15:30:00-05:00',
             'end':'2026-11-12T16:00:00-05:00','status':'CLOSED','close':4.152}],
             scoring={'score':85})
    return s


def reference(close=.2076):
    return {'close':close,'session_date':'2026-11-12','closed_at':'2026-11-12T16:00:00-05:00'}


def series(count,up=True):
    rows=[]
    for n in range(count):
        at=NOW-timedelta(days=count-n)
        rows.append({'time':at.isoformat(),'end':(at+timedelta(hours=1)).isoformat(),
                     'status':'CLOSED','close':float(100+n if up else 1000-n)})
    return rows


class PriceBasisTests(unittest.TestCase):
    def test_cosm_reverse_split_cannot_be_a_1740_percent_rise(self):
        s=snap();result=facts.price_basis(s,reference())
        self.assertEqual(result['status'],'ACTION_SCALE_MISMATCH');self.assertTrue(result['blocked'])
        self.assertEqual(s['price'],3.82)

    def test_same_fetch_adjusted_reference_is_not_adjusted_twice(self):
        result=facts.price_basis(snap(),reference(4.152))
        self.assertEqual(result['status'],'ACTION_BASIS_VERIFIED');self.assertFalse(result['blocked'])

    def test_forward_split_also_detects_old_share_unit(self):
        s=snap();s.update(price=5.,corporate_actions=[action(4)])
        s['chart_history'][-1]['close']=5.
        self.assertEqual(facts.price_basis(s,reference(20))['status'],'ACTION_SCALE_MISMATCH')

    def test_large_gap_is_not_evidence_of_split(self):
        s=snap();s['corporate_actions']=[]
        result=facts.price_basis(s,reference())
        self.assertEqual(result['status'],'UNEXPLAINED_PRICE_DISCONTINUITY');self.assertFalse(result['events'])

    def test_future_action_and_later_observation_are_not_used(self):
        s=snap();s['corporate_actions'][0]['observed_at']=(NOW+timedelta(minutes=1)).isoformat()
        result=facts.price_basis(s,reference(4))
        self.assertEqual(result['status'],'NO_ACTION_REPORTED')
        s['corporate_actions'][0].update(observed_at=NOW.isoformat(),effective_at=(NOW+timedelta(days=1)).isoformat())
        self.assertFalse(facts.price_basis(s,reference(4))['events'])

    def test_action_without_comparable_prior_candle_quarantines(self):
        s=snap();s['chart_history']=[]
        self.assertEqual(facts.price_basis(s,reference())['status'],'ACTION_BASIS_UNVERIFIED')

    def test_actions_come_from_frame_not_additional_provider_query(self):
        frame=pd.DataFrame({'Stock Splits':[0,.05,2]},index=pd.to_datetime(['2026-11-12','2026-11-13','2026-11-14'],utc=True))
        rows=facts.yahoo_actions(frame,NOW.isoformat())
        self.assertEqual(len(rows),1);self.assertEqual(rows[0]['new_per_old'],.05)

    def test_missing_action_column_does_not_invent_actions(self):
        self.assertEqual(facts.yahoo_actions(pd.DataFrame({'Close':[5]}),NOW.isoformat()),[])


class TrendTests(unittest.TestCase):
    def test_all_daily_horizons_have_independent_minimum_history(self):
        s=snap();s['corporate_actions']=[]
        short=facts.trends(s,series(30),{'blocked':False})['horizons']
        self.assertEqual(short['short']['direction'],'UP')
        self.assertEqual(short['long']['direction'],'UNKNOWN')
        long=facts.trends(s,series(240),{'blocked':False})['horizons']
        self.assertEqual(long['long']['direction'],'UP')
        self.assertEqual(long['session']['direction'],'UNKNOWN')

    def test_rebound_inside_downtrend_is_not_reversal(self):
        rows=series(240,False)
        for n,r in enumerate(rows[-25:]):r['close']=750+n*1.2
        result=facts.trends(snap(),rows,{'blocked':False})
        self.assertEqual(result['horizons']['short']['direction'],'UP')
        self.assertEqual(result['horizons']['long']['direction'],'DOWN')
        self.assertIn('odwrócenie',result['relationship'])

    def test_flat_series_mixed_not_bullish(self):
        rows=series(240)
        for row in rows:row['close']=5.
        self.assertEqual(facts.trends(snap(),rows,{'blocked':False})['horizons']['long']['direction'],'MIXED')

    def test_future_open_duplicate_and_nan_bars_cannot_create_history(self):
        rows=series(24);rows += [rows[0],{'time':NOW.isoformat(),'end':(NOW+timedelta(hours=1)).isoformat(),'status':'CLOSED','close':999}]
        rows.append({**rows[1],'status':'OPEN'});rows.append({**rows[2],'close':float('nan')})
        result=facts.trends(snap(),rows,{'blocked':False})
        self.assertEqual(result['horizons']['short']['bars'],24)
        self.assertEqual(result['horizons']['short']['direction'],'UNKNOWN')

    def test_blocked_basis_makes_all_horizons_unavailable(self):
        result=facts.trends(snap(),series(240),{'blocked':True,'reason':'Niespójna jednostka'})
        self.assertTrue(all(h['direction']=='UNKNOWN' for h in result['horizons'].values()))

    def test_intraday_uses_this_session_only(self):
        s=snap();s['candle_time']='2026-11-13T13:30:00-05:00'
        self.assertEqual(facts.trends(s,[],{'blocked':False})['horizons']['session']['bars'],0)

    def test_mobile_cards_escape_source_data_and_keep_text_labels(self):
        s=snap();s['trend_context']=facts.trends(s,series(240),{'blocked':False})
        s['news_watch']={'label':'<script>bad</script>'}
        markup=facts.cards(s)
        self.assertIn('flex-wrap:wrap',markup);self.assertIn('Wzrostowy',markup)
        self.assertNotIn('<script>',markup)


class IntegrationTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        self.store=KI.Store(Path(temp.name)/'test.sqlite3')
        self.store.save_section('settings',{'pipeline_enabled':True,'telegram_enabled':True,'price_threshold_pct':2.})
        self.store.save_section('tickers',['COSM'])
        KI._save_daily_history(self.store,'COSM',[{'session_date':'2026-11-12','status':'CLOSED',
            'open':.2076,'high':.22,'low':.2,'close':.2076,'volume':10000}],NOW)

    def enqueue(self,s=None):return watch.enqueue(KI,self.store,s or snap(),NOW.isoformat())

    def test_detector_saves_quarantine_without_signal_confirmation(self):
        s=snap();facts.attach(KI,self.store,s)
        result=KI.detect_market(self.store,s,{'price_matrix_enabled':True})
        self.assertEqual(result['status'],'PRICE_BASIS_BLOCKED')
        self.assertIsNone(result['price_matrix']['change_pct'])
        with self.store.connection() as c:
            self.assertEqual(c.execute('SELECT count(*) FROM signal_confirmations').fetchone()[0],0)
            saved=KI.load_payload(c.execute('SELECT payload FROM observations').fetchone()[0])
        self.assertTrue(saved['price_basis']['blocked'])

    def test_manifest_orchestrator_and_reader_share_block(self):
        s=snap();facts.attach(KI,self.store,s)
        m=KI.build_analysis_manifest({'snapshot':s,'autonomous_assessment_version':1},{'sources':[]})
        result=company_orchestrator.assess(KI,s,m,{},NOW)
        self.assertEqual(result['reason'],'PRICE_BASIS_BLOCKED');self.assertFalse(result['review_allowed'])
        self.assertEqual(m['trade_plan']['status'],'UNAVAILABLE')
        self.assertIn('trend_context',ki_assistant.SNAP_FIELDS)

    def test_high_score_queues_without_confirmed_move_or_ai_job(self):
        s=snap();s['corporate_actions']=[];s['price_matrix']={'state':'MONITORING','change_pct':.1}
        self.assertTrue(self.enqueue(s));self.assertIsNone(self.enqueue(s))
        with self.store.connection() as c:
            self.assertEqual(c.execute('SELECT count(*) FROM analysis_jobs').fetchone()[0],0)
            self.assertEqual(c.execute('SELECT reason FROM issuer_watch_jobs').fetchone()[0],'HIGH_SCORE')

    def test_automat_directional_score_also_triggers_independent_research(self):
        s=snap();s.update(corporate_actions=[],scoring={'score':50},price_matrix={'state':'MONITORING','change_pct':1.})
        with patch.object(KI,'opportunity_local_rank',return_value={'score':85}):
            self.assertTrue(self.enqueue(s))
        self.assertEqual(s['news_watch']['trigger_scores']['directional_score'],85)
        with self.store.connection() as c:
            self.assertEqual(c.execute('SELECT reason FROM issuer_watch_jobs').fetchone()[0],'HIGH_SCORE')

    def test_portfolio_news_does_not_require_score(self):
        KI.portfolio_save(self.store,[{'ticker':'COSM','sl':None,'tp':None}])
        s=snap();s.update(corporate_actions=[],scoring={'score':None})
        self.assertTrue(self.enqueue(s))
        with self.store.connection() as c:self.assertEqual(c.execute('SELECT reason FROM issuer_watch_jobs').fetchone()[0],'PORTFOLIO')

    def test_disabled_pipeline_never_enqueues(self):
        self.store.update_settings({'pipeline_enabled':False})
        self.assertIsNone(self.enqueue())

    def test_missing_key_does_not_call_provider(self):
        self.enqueue()
        with patch('tavily_cli_adapter.search_sync',side_effect=AssertionError('network')):
            self.assertTrue(watch.process_once(KI,self.store,{},NOW.isoformat()))
        with self.store.connection() as c:self.assertEqual(c.execute('SELECT state FROM issuer_watch_jobs').fetchone()[0],'KEY_MISSING')

    def test_daily_quota_is_checked_before_provider(self):
        self.enqueue()
        with self.store.transaction() as c:
            for n in range(24):
                c.execute('INSERT INTO issuer_watch_jobs VALUES(?,?,?,?,?,?,?,?,?,?)',
                    ('used'+str(n),'AAA','FAILED','HIGH_SCORE','{}',NOW.isoformat(),NOW.isoformat(),NOW.isoformat(),None,None))
        with patch('tavily_cli_adapter.search_sync',side_effect=AssertionError('network')):
            watch.process_once(KI,self.store,{'TAVILY_API_KEY':'fixture'},NOW.isoformat())
        with self.store.connection() as c:self.assertEqual(c.execute("SELECT state FROM issuer_watch_jobs WHERE ticker='COSM'").fetchone()[0],'LIMIT_REACHED')

    def test_failed_call_is_not_retried(self):
        self.enqueue()
        with patch('tavily_cli_adapter.search_sync',side_effect=OSError('fixture failure')) as provider:
            watch.process_once(KI,self.store,{'TAVILY_API_KEY':'fixture'},NOW.isoformat())
            watch.process_once(KI,self.store,{'TAVILY_API_KEY':'fixture'},NOW.isoformat())
        self.assertEqual(provider.call_count,1)

    def test_rejected_sources_explicit_and_no_telegram(self):
        self.enqueue()
        with patch('tavily_cli_adapter.search_sync',return_value={'results':[]}),patch.object(KI,'normalize_tavily_context',return_value={'sources':[],'excluded':2}):
            watch.process_once(KI,self.store,{'TAVILY_API_KEY':'fixture'},NOW.isoformat())
        with self.store.connection() as c:
            self.assertEqual(c.execute('SELECT state FROM issuer_watch_jobs').fetchone()[0],'NO_ACCEPTED_SOURCES')
            self.assertEqual(c.execute('SELECT count(*) FROM outbox').fetchone()[0],0)

    def test_action_notice_is_deduplicated_and_uses_existing_sender_even_with_final_mode(self):
        s=snap();facts.attach(KI,self.store,s)
        self.store.update_settings({'final_company_review_enabled':True})
        watch.action_notice(KI,self.store,s);watch.action_notice(KI,self.store,s)
        with self.store.connection() as c:
            self.assertEqual(c.execute('SELECT count(*) FROM outbox').fetchone()[0],1)
        self.assertEqual(KI.claim_delivery(self.store,now=NOW)['kind'],'ISSUER_NOTICE')

    def test_no_action_notice_when_telegram_disabled(self):
        s=snap();facts.attach(KI,self.store,s)
        self.store.update_settings({'telegram_enabled':False})
        watch.action_notice(KI,self.store,s)
        with self.store.connection() as c:self.assertEqual(c.execute('SELECT count(*) FROM outbox').fetchone()[0],0)

    def test_split_cannot_fire_old_portfolio_take_profit(self):
        s=snap();facts.attach(KI,self.store,s)
        KI.detect_market(self.store,s,{'price_matrix_enabled':True})
        KI.portfolio_save(self.store,[{'ticker':'COSM','sl':.15,'tp':.3}])
        self.assertEqual(KI.portfolio_check_alerts(self.store,NOW.isoformat()),0)

    def test_every_local_plan_entry_point_respects_price_basis_block(self):
        import tracking_view,scenario_plan
        s=snap();facts.attach(KI,self.store,s)
        self.assertEqual(KI.build_trade_plan(s,1740.,now=NOW)['status'],'UNAVAILABLE')
        self.assertIn('jednostki',tracking_view.level_view(s,1740.,now=NOW)['plan']['reason'])
        self.assertEqual(scenario_plan.build(s,[],[])['status'],'UNAVAILABLE')
        self.assertFalse(KI.portfolio_price_status(s,NOW.isoformat())[0])

    def test_cached_research_never_uses_future_results(self):
        self.enqueue()
        response={'results':[]}
        with patch('tavily_cli_adapter.search_sync',return_value=response),patch.object(KI,'normalize_tavily_context',return_value={'sources':[]}):
            watch.process_once(KI,self.store,{'TAVILY_API_KEY':'fixture'},NOW.isoformat())
        self.assertIsNone(watch.cached_search(KI,self.store,snap(),(NOW-timedelta(seconds=1)).isoformat()))
        self.assertIsNotNone(watch.cached_search(KI,self.store,snap(),(NOW+timedelta(minutes=10)).isoformat()))

    def test_official_cosm_source_is_accepted_by_actual_identity_validator(self):
        response={'results':[{'title':'Cosmos Health Inc. (COSM) Reverse Stock Split',
            'url':'https://www.nasdaqtrader.com/TraderNews.aspx?id=ECA2026-812',
            'published_date':'Wed, 11 Nov 2026 20:00:00 GMT',
            'content':'Cosmos Health Inc. (COSM) will effect a one-for-twenty reverse stock split on November 13, 2026.'}]}
        context=KI.normalize_tavily_context(response,snap(),window_days=30)
        self.assertEqual(len(context['sources']),1)

    def test_refresh_reference_only_fetches_once_and_never_synthesizes_adjustment(self):
        s=snap();facts.attach(KI,self.store,s)
        with patch.object(KI,'fetch_market',side_effect=OSError('no provider')) as provider:
            facts.refresh_blocked_reference(KI,self.store,s)
            facts.refresh_blocked_reference(KI,self.store,s)
        self.assertEqual(provider.call_count,1)
        self.assertTrue(s['price_basis']['blocked'])
        with self.store.connection() as c:
            self.assertAlmostEqual(c.execute('SELECT close FROM daily_candles').fetchone()[0],.2076)

    def test_public_feed_is_separate_from_search_and_has_hourly_reservation(self):
        corporate_feed.schedule(KI,self.store,NOW.isoformat())
        self.assertTrue(corporate_feed.pending(KI,self.store))
        with patch.object(corporate_feed,'fetch',return_value=feed_xml()),patch('tavily_cli_adapter.search_sync',side_effect=AssertionError('paid provider')):
            corporate_feed.process_once(KI,self.store,NOW.isoformat())
        corporate_feed.schedule(KI,self.store,(NOW+timedelta(minutes=10)).isoformat())
        self.assertFalse(corporate_feed.pending(KI,self.store))
        with self.store.connection() as c:
            self.assertEqual(c.execute('SELECT count(*) FROM outbox').fetchone()[0],1)
            saved=KI.load_payload(c.execute('SELECT payload FROM runtime WHERE key=?',('market_intelligence:official:COSM',)).fetchone()[0])
            self.assertEqual(saved['sources'][0]['status'],'OFFICIAL_HEADLINE')

    def test_public_feed_failure_does_not_claim_no_news(self):
        corporate_feed.schedule(KI,self.store,NOW.isoformat())
        with patch.object(corporate_feed,'fetch',side_effect=OSError('fixture')):
            corporate_feed.process_once(KI,self.store,NOW.isoformat())
        with self.store.connection() as c:
            data=KI.load_payload(c.execute('SELECT payload FROM runtime WHERE key=?',(corporate_feed.KEY,)).fetchone()[0])
        self.assertEqual(data['state'],'FAILED')

    def test_whole_market_cycle_quarantines_split_but_schedules_independent_news(self):
        s=snap()
        with (patch.object(KI,'fetch_automatic_snapshot',return_value=s),patch.object(KI,'fetch_market',side_effect=OSError('fixture')),
             patch.object(KI,'maintain_signal_history'),patch.object(KI,'daily_report_send'),patch.object(KI,'us_report_send')):
            result=KI.run_market_cycle(self.store)
        self.assertEqual(result['results'][0]['status'],'PRICE_BASIS_BLOCKED')
        self.assertTrue(watch.pending(self.store));self.assertTrue(corporate_feed.pending(KI,self.store))
        with self.store.connection() as c:
            self.assertEqual(c.execute('SELECT count(*) FROM analysis_jobs').fetchone()[0],0)
            self.assertEqual(c.execute("SELECT count(*) FROM outbox WHERE kind='ISSUER_NOTICE'").fetchone()[0],1)

    def test_normal_analysis_reuses_independent_search_without_second_search_charge(self):
        self.enqueue()
        with patch('tavily_cli_adapter.search_sync',return_value={'results':[]}),patch.object(KI,'normalize_tavily_context',return_value={'sources':[]}):
            watch.process_once(KI,self.store,{'TAVILY_API_KEY':'fixture'},NOW.isoformat())
        s=snap();s['acquired_at']=(NOW+timedelta(minutes=5)).isoformat()
        with self.store.transaction() as c:
            c.execute('INSERT INTO events VALUES(?,?,?,?,?)',('event','COSM','1h',s['acquired_at'],KI.json_text({'snapshot':s})))
        with (patch('tavily_cli_adapter.search_sync',side_effect=AssertionError('second Search')),
             patch('tavily_cli_adapter.enrich_search_response')):
            KI.submit_event_research(self.store,'event','Cosmos Health Inc.',s['acquired_at'],'fixture')
        self.assertEqual(KI.load_event_research(self.store,'event')['state'],'COMPLETED')

    def test_interrupted_search_keeps_budget_reservation_and_visible_error(self):
        key=self.enqueue()
        with self.store.transaction() as c:
            c.execute("UPDATE issuer_watch_jobs SET state='RUNNING',started_at=? WHERE id=?",(NOW.isoformat(),key))
        watch.recover(KI,self.store)
        with self.store.connection() as c:
            job=c.execute('SELECT state,started_at FROM issuer_watch_jobs').fetchone()
            status=KI.load_payload(c.execute('SELECT payload FROM runtime WHERE key=?',('market_intelligence:news:COSM',)).fetchone()[0])
        self.assertEqual(job['state'],'FAILED');self.assertEqual(job['started_at'],NOW.isoformat())
        self.assertEqual(status['status'],'FAILED')

    def test_daily_trend_cache_in_old_units_is_not_merged_into_new_reference(self):
        with self.store.transaction() as c:
            c.execute('UPDATE daily_candles SET open=open*20,high=high*20,low=low*20,close=close*20 WHERE ticker=?',('COSM',))
            c.execute('INSERT INTO runtime VALUES(?,?,?)',('market_intelligence:daily:COSM',KI.json_text({
                'acquired_at':(NOW-timedelta(hours=3)).isoformat(),
                'rows':[{'time':'2026-11-12T00:00:00-05:00','end':'2026-11-12T16:00:00-05:00','status':'CLOSED','close':.2076}]}),NOW.isoformat()))
        s=snap();facts.attach(KI,self.store,s)
        self.assertFalse(s['price_basis']['blocked'])
        self.assertEqual(s['trend_context']['horizons']['long']['bars'],0)

    def test_exhausted_daily_budget_does_not_accumulate_unbounded_jobs(self):
        with self.store.transaction() as c:
            for n in range(24):
                c.execute('INSERT INTO issuer_watch_jobs VALUES(?,?,?,?,?,?,?,?,?,?)',
                    ('used'+str(n),'AAA','FAILED','HIGH_SCORE','{}',NOW.isoformat(),NOW.isoformat(),NOW.isoformat(),None,None))
        self.assertIsNone(self.enqueue())
        with self.store.connection() as c:
            self.assertEqual(c.execute('SELECT count(*) FROM issuer_watch_jobs').fetchone()[0],24)
            status=KI.load_payload(c.execute('SELECT payload FROM runtime WHERE key=?',('market_intelligence:news:COSM',)).fetchone()[0])
        self.assertEqual(status['status'],'LIMIT_REACHED')


def feed_xml(title='Information Regarding Reverse Stock Split for Cosmos Health Inc. (COSM)',url='http://www.nasdaqtrader.com/TraderNews.aspx?id=ECA2026-812',date='Wed, 11 Nov 2026 20:00:00 GMT'):
    return ('<rss><channel><item><title>'+title+'</title><link>'+url+'</link><pubDate>'+date+'</pubDate></item></channel></rss>').encode()


class CorporateFeedTests(unittest.TestCase):
    def test_exact_parenthesized_ticker_and_official_url_are_both_required(self):
        rows=corporate_feed.parse(feed_xml(),['COSM'],NOW.isoformat())
        self.assertEqual(rows[0]['ticker'],'COSM');self.assertTrue(rows[0]['url'].startswith('https:'))
        self.assertEqual(corporate_feed.parse(feed_xml(title='(COSMO)'),['COSM'],NOW.isoformat()),[])
        self.assertEqual(corporate_feed.parse(feed_xml(url='https://attacker.invalid/TraderNews.aspx?id=ECA2026-812'),['COSM'],NOW.isoformat()),[])

    def test_future_or_old_headline_never_triggers_notice(self):
        for date in ('Sat, 14 Nov 2026 20:00:00 GMT','Sun, 01 Nov 2026 20:00:00 GMT'):
            self.assertEqual(corporate_feed.parse(feed_xml(date=date),['COSM'],NOW.isoformat()),[])

    def test_unrelated_ticker_never_matches_from_description(self):
        self.assertEqual(corporate_feed.parse(feed_xml(),['STX.WA','HUMA'],NOW.isoformat()),[])


if __name__=='__main__':unittest.main()
