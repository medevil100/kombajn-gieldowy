import copy
import json
import unittest
from unittest.mock import patch
import KI
import test_large_movement_20261113 as fixtures
from test_large_movement_20261113 import NOW,daily_sample
from uzupelnij_52_tyg_20261113 import replenish,listed_tickers

class BackfillTests(unittest.TestCase):
    def setUp(self):
        self.fixture=fixtures.LargeMovementTests();self.fixture.setUp();self.addCleanup(self.fixture.doCleanups)
        self.store=self.fixture.store

    def response(self):
        return {'daily_history':daily_sample(250),'history_attempts':[{'period':'1y'}],
                'acquired_at':NOW.isoformat(),'source':'Yahoo Finance'}

    def test_expands_old_history_and_cache_without_model(self):
        with patch.object(KI,'fetch_market',return_value=self.response()) as fetch,patch.object(KI,'service_http',side_effect=AssertionError('paid call')):
            result=replenish(KI,self.store,'AAA',NOW.isoformat())
            self.assertEqual(result['sessions'],250);self.assertEqual(result['status'],'FETCHED')
            self.assertEqual(replenish(KI,self.store,'AAA',NOW.isoformat())['status'],'RANGE_ALREADY_COVERED')
            fetch.assert_called_once_with('AAA','1d')
        with self.store.connection() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM daily_candles WHERE ticker='AAA'").fetchone()[0],250)
            self.assertEqual(db.execute('SELECT count(*) FROM analysis_jobs').fetchone()[0],0)

    def test_partial_provider_history_is_explicit(self):
        response=self.response();response['daily_history']=daily_sample(79)
        with patch.object(KI,'fetch_market',return_value=response):result=replenish(KI,self.store,'AAA',NOW.isoformat())
        self.assertEqual(result['coverage'],'SHORTER_SOURCE_HISTORY')

    def test_invalid_batch_keeps_prior_cache_and_rows(self):
        response=self.response();response['daily_history'][0]['high']=.001
        with patch.object(KI,'fetch_market',return_value=response):result=replenish(KI,self.store,'AAA',NOW.isoformat())
        self.assertEqual(result['status'],'FAILED')
        with self.store.connection() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM daily_candles WHERE ticker='AAA'").fetchone()[0],80)

    def test_all_saved_tickers_including_new_one_without_any_case(self):
        self.store.save_section('tickers',['AAA','STX.WA','NEW'])
        with self.store.connection() as db:
            self.assertEqual(set(listed_tickers(db)),{'AAA','STX.WA','NEW'})
            self.assertEqual(db.execute('SELECT count(*) FROM large_movement_cases').fetchone()[0],0)

    def test_failed_attempt_does_not_loop_or_call_other_providers(self):
        with patch.object(KI,'fetch_market',side_effect=OSError('offline')) as fetch:
            self.assertEqual(replenish(KI,self.store,'AAA',NOW.isoformat())['status'],'FAILED')
            self.assertEqual(replenish(KI,self.store,'AAA',NOW.isoformat())['status'],'COOLDOWN')
            self.assertEqual(fetch.call_count,1)

    def test_unattempted_new_ticker_is_prioritized(self):
        self.store.save_section('tickers',['AAA','ZZZ'])
        with patch.object(KI,'fetch_market',side_effect=OSError('offline')):replenish(KI,self.store,'AAA',NOW.isoformat())
        with self.store.connection() as db:self.assertEqual(listed_tickers(db),['ZZZ','AAA'])

    def test_daily_limit_stops_before_yahoo(self):
        with self.store.transaction() as db:
            for n in range(48):db.execute('INSERT INTO runtime VALUES(?,?,?)',('history_52w_backfill:X'+str(n),KI.json_text({'attempted_at':NOW.isoformat()}),NOW.isoformat()))
        with patch.object(KI,'fetch_market',side_effect=AssertionError('provider')):
            self.assertEqual(replenish(KI,self.store,'AAA',NOW.isoformat())['status'],'DAILY_LIMIT')

    def test_rate_limit_stops_other_tickers_for_one_hour(self):
        with patch.object(KI,'fetch_market',side_effect=KI.MarketRateLimitError('429')) as fetch:
            self.assertEqual(replenish(KI,self.store,'AAA',NOW.isoformat())['status'],'FAILED')
            self.assertEqual(replenish(KI,self.store,'BBB',NOW.isoformat())['status'],'SOURCE_BACKOFF')
            self.assertEqual(fetch.call_count,1)

if __name__=='__main__':unittest.main()
