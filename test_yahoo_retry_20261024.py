"""Regresje Yahoo i planowania ponowień: bez sieci, mocków i atrap usług."""
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import KI


class YahooRetryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store=KI.Store(Path(self.tmp.name)/'retry.sqlite3')
        self.now=datetime(2026,10,12,8,30,tzinfo=timezone.utc)

    def seed(self,now=None):
        KI._save_daily_history(self.store,'STX.WA',[{'session_date':'2026-10-09','status':'CLOSED',
            'open':1.,'high':1.1,'low':.9,'close':1.,'volume':1000}],now or self.now)

    def test_daily_rejected_rows_do_not_discard_valid_history(self):
        # Shape observed in the real CHP.WA and GTBP responses: an empty past row
        # and a future record coexist with valid daily sessions.
        index=pd.DatetimeIndex(['2026-10-08','2026-10-09','2026-10-12','2034-10-08'],tz='Europe/Warsaw')
        frame=pd.DataFrame({'Open':[1.,None,1.2,0.], 'High':[1.1,None,1.3,0.],
            'Low':[.9,None,1.1,0.], 'Close':[1.,None,1.2,.42], 'Volume':[1000.,0.,2000.,0.]},index=index)
        rejected=[];now=self.now+timedelta(days=1)
        rows=KI.normalize_yahoo_frame(frame,'STX.WA','1d',now,{},rejected_rows=rejected)
        self.assertEqual(len(rows),2)
        self.assertEqual(len(rejected),2)
        self.assertEqual(rows[-1]['close'],1.2)
        self.assertEqual(rejected[-1]['time'],'2034-10-08T00:00:00+02:00')
        KI._save_daily_history(self.store,'STX.WA',rows,now,source_diagnostics=rejected)
        self.assertEqual(len(KI.load_daily_candles(self.store,'STX.WA')),2)
        with self.store.connection() as c:
            payload=c.execute("SELECT payload FROM runtime WHERE key='daily_history:STX.WA'").fetchone()[0]
        self.assertIn('2034-10-08',payload)

    def test_strict_normalizer_still_rejects_future_rows(self):
        frame=pd.DataFrame({'Open':[1.], 'High':[1.], 'Low':[1.], 'Close':[1.], 'Volume':[0.]},
            index=pd.DatetimeIndex(['2034-10-08'],tz='Europe/Warsaw'))
        with self.assertRaises(ValueError):KI.normalize_yahoo_frame(frame,'STX.WA','1d',self.now,{})

    def test_longer_history_does_not_replace_valid_recent_session_with_old_tail(self):
        # AME.WA: 3mo supplied October 23; the 1y response had missing closes
        # after May 26. Extending history must retain the actual October row.
        recent=[{'time':'2026-10-23T00:00:00+02:00','close':2.18}]
        extended=[{'time':'2026-05-26T00:00:00+02:00','close':2.02}]
        rows=KI.merge_daily_source_rows(recent,extended)
        self.assertEqual(len(rows),2)
        self.assertEqual(rows[-1],recent[0])
        self.assertEqual(KI.merge_daily_source_rows(recent,[{**recent[0],'close':1.}])[-1]['close'],2.18)

    def test_no_valid_daily_data_never_creates_a_price(self):
        frame=pd.DataFrame({'Open':[None], 'High':[None], 'Low':[None], 'Close':[None], 'Volume':[0.]},
            index=pd.DatetimeIndex(['2026-10-09'],tz='Europe/Warsaw'))
        rejected=[]
        with self.assertRaises(ValueError):
            KI.normalize_yahoo_frame(frame,'STX.WA','1d',self.now,{},rejected_rows=rejected)
        self.assertEqual(len(rejected),1)
        self.assertEqual(KI.load_daily_candles(self.store,'STX.WA'),[])

    def test_retry_backoff_is_persistent_and_interval_specific(self):
        error=KI.MarketDataUnavailable('NO_OHLCV','Brak danych Yahoo — ticker wymaga weryfikacji.')
        first=KI.record_market_fetch(self.store,'STX.WA','1h',error,self.now)
        self.assertEqual(KI.parse_market_time(first['next_attempt_at']),self.now+timedelta(minutes=15))
        self.store=KI.Store(self.store.path)
        self.assertFalse(KI.market_fetch_due(self.store,'STX.WA','1h',self.now+timedelta(minutes=14)))
        self.assertTrue(KI.market_fetch_due(self.store,'STX.WA','1h',self.now+timedelta(minutes=15)))
        self.assertTrue(KI.market_fetch_due(self.store,'STX.WA','1d',self.now))
        second=KI.record_market_fetch(self.store,'STX.WA','1h',error,self.now+timedelta(minutes=15))
        self.assertEqual(KI.parse_market_time(second['next_attempt_at']),self.now+timedelta(minutes=45))
        self.assertEqual(second['failures'],2)

    def test_success_resets_retry_count_without_changing_other_instrument(self):
        error=KI.MarketDataUnavailable('MISSING_PRICE','Brak ceny.')
        KI.record_market_fetch(self.store,'STX.WA','1h',error,self.now)
        KI.record_market_fetch(self.store,'OTHER.WA','1h',error,self.now)
        state=KI.record_market_fetch(self.store,'STX.WA','1h',now=self.now+timedelta(minutes=15))
        self.assertEqual(state['failures'],0)
        self.assertIsNone(state['next_attempt_at'])
        self.assertEqual(KI.market_fetch_state(self.store,'OTHER.WA','1h')['failures'],1)

    def test_weekend_retry_waits_for_monday_and_respects_dst(self):
        now=datetime(2026,10,24,11,tzinfo=timezone.utc)
        for ticker,expected in [('STX.WA','2026-10-26T08:00:00+00:00'),('AAA','2026-10-26T13:30:00+00:00')]:
            state=KI.record_market_fetch(self.store,ticker,'1h',KI.MarketDataUnavailable('NO_OHLCV','Brak danych.'),now)
            self.assertEqual(state['next_attempt_at'],expected)
            self.assertFalse(KI.market_fetch_due(self.store,ticker,'1h',now+timedelta(days=1)))

    def test_successful_hourly_read_outside_session_is_also_not_repeated(self):
        now=datetime(2026,10,24,11,tzinfo=timezone.utc)
        state=KI.record_market_fetch(self.store,'STX.WA','1h',now=now)
        self.assertEqual(state['status'],'OK')
        self.assertEqual(state['next_attempt_at'],'2026-10-26T08:00:00+00:00')

    def test_friday_completed_daily_refresh_does_not_repeat_on_weekend(self):
        friday=datetime(2026,10,23,16,tzinfo=timezone.utc)
        self.seed(friday)
        self.assertFalse(KI.daily_history_refresh_due(self.store,'STX.WA',friday+timedelta(days=1)))
        self.assertFalse(KI.daily_history_refresh_due(self.store,'STX.WA',friday+timedelta(days=2)))
        self.assertTrue(KI.daily_history_refresh_due(self.store,'STX.WA',friday+timedelta(days=3)))

    def test_friday_preclose_daily_refresh_still_refreshes_closed_session(self):
        friday=datetime(2026,10,23,12,tzinfo=timezone.utc)
        self.seed(friday)
        self.assertTrue(KI.daily_history_refresh_due(self.store,'STX.WA',friday+timedelta(days=1)))

    def test_deferred_fetch_stops_before_any_provider_call(self):
        self.seed()
        error=KI.MarketDataUnavailable('NO_OHLCV','Brak danych.')
        KI.record_market_fetch(self.store,'STX.WA','1h',error,self.now)
        with self.assertRaises(KI.MarketFetchDeferred) as caught:
            KI.fetch_automatic_snapshot(self.store,'STX.WA',self.now+timedelta(minutes=1))
        self.assertEqual(caught.exception.state['error_code'],'NO_OHLCV')

    def test_missing_reference_and_daily_backoff_prevent_hourly_request(self):
        KI.record_market_fetch(self.store,'STX.WA','1d',KI.MarketDataUnavailable('NO_OHLCV','Brak danych.'),self.now)
        with self.assertRaises(KI.MarketFetchDeferred):
            KI.fetch_automatic_snapshot(self.store,'STX.WA',self.now+timedelta(minutes=1))
        self.assertEqual(KI.market_fetch_state(self.store,'STX.WA','1h'),{})


if __name__=='__main__':unittest.main(verbosity=2)
