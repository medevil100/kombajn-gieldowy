"""Daily-source recovery follows attempt cadence, not response-finish jitter."""
from datetime import datetime,timedelta,timezone
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import KI


class DailyRefreshBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.store=KI.Store(Path(self.temp.name)/'daily.sqlite3')
        self.start=datetime(2026,11,10,8,tzinfo=timezone.utc)
        self.current=self.start;self.daily_calls=[];self.day='2026-11-06'

    def rows(self):
        return [{'session_date':self.day,'status':'CLOSED','open':1.9,'high':2.,'low':1.8,'close':1.948,'volume':1000.}]

    def fetch(self,ticker,interval):
        if interval=='1d':
            self.daily_calls.append(self.current)
            return {'acquired_at':(self.current+timedelta(milliseconds=200)).isoformat(),'daily_history':self.rows()}
        return {'ticker':ticker,'acquired_at':(self.current+timedelta(milliseconds=300)).isoformat()}

    def run_at(self,minute):
        self.current=self.start+timedelta(minutes=minute)
        with patch.object(KI,'fetch_market',side_effect=self.fetch):
            return KI.fetch_automatic_snapshot(self.store,'STX.WA',self.current)

    def test_incomplete_success_is_retried_in_each_next_cycle(self):
        for minute in (0,15,30):self.run_at(minute)
        self.assertEqual(self.daily_calls,[self.start+timedelta(minutes=m) for m in (0,15,30)])
        with self.store.connection() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM analysis_jobs').fetchone()[0],0)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM outbox').fetchone()[0],0)

    def test_incomplete_response_cannot_cause_repeated_fetches_inside_cycle(self):
        for minute in (0,1,14):self.run_at(minute)
        self.assertEqual(len(self.daily_calls),1)
        self.run_at(15)
        self.assertEqual(len(self.daily_calls),2)

    def test_subsecond_cycle_start_jitter_does_not_skip_a_whole_cycle(self):
        self.run_at(0)
        self.run_at(15-0.2/60)
        self.assertEqual(len(self.daily_calls),2)

    def test_complete_previous_session_stops_intraday_retries(self):
        self.day='2026-11-09'
        for minute in (0,15,30,60):self.run_at(minute)
        self.assertEqual(len(self.daily_calls),1)

    def test_legacy_history_without_attempt_timestamp_keeps_its_cooldown(self):
        KI._save_daily_history(self.store,'STX.WA',self.rows(),self.start)
        self.assertFalse(KI.daily_history_refresh_due(self.store,'STX.WA',self.start+timedelta(minutes=14)))
        self.assertTrue(KI.daily_history_refresh_due(self.store,'STX.WA',self.start+timedelta(minutes=15)))

    def test_provider_error_backoff_is_not_bypassed(self):
        KI._save_daily_history(self.store,'STX.WA',self.rows(),self.start-timedelta(minutes=15))
        def failing(ticker,interval):
            if interval=='1d':
                self.daily_calls.append(self.current)
                raise KI.MarketDataUnavailable('NO_DATA','fixture')
            return self.fetch(ticker,interval)
        with patch.object(KI,'fetch_market',side_effect=failing):
            for minute in (0,14,15,30,44):
                self.current=self.start+timedelta(minutes=minute)
                KI.fetch_automatic_snapshot(self.store,'STX.WA',self.current)
        self.assertEqual(self.daily_calls,[self.start,self.start+timedelta(minutes=15)])
        self.assertEqual(KI.market_fetch_state(self.store,'STX.WA','1d')['next_attempt_at'],
                         (self.start+timedelta(minutes=45)).isoformat())


if __name__=='__main__':unittest.main()
