"""Report scheduling against exchange calendars and a disposable SQLite outbox."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import KI
from report_schedule import report_window


def at(value):
    return datetime.fromisoformat(value.replace('Z', '+00:00'))


class ReportScheduleTests(unittest.TestCase):
    def test_winter_never_sends_an_hour_before_close(self):
        for market, early, due in (
            ('GPW', '2026-11-09T15:10Z', '2026-11-09T16:05Z'),
            ('USA', '2026-11-09T20:10Z', '2026-11-09T21:05Z'),
        ):
            with self.subTest(market=market):
                self.assertIsNone(report_window(market, at(early)))
                self.assertEqual(report_window(market, at(due))['due_at'], at(due).isoformat())

    def test_summer_and_independent_us_eu_clock_changes(self):
        for day, gpw, usa in (
            ('2026-07-06', '15:05', '20:05'),
            ('2026-03-16', '16:05', '20:05'),
            ('2026-10-26', '16:05', '20:05'),
        ):
            for market, hour in (('GPW', gpw), ('USA', usa)):
                due=at(day+'T'+hour+'Z')
                with self.subTest(day=day, market=market):
                    self.assertIsNone(report_window(market, due-timedelta(seconds=1)))
                    self.assertEqual(report_window(market, due)['due_at'], due.isoformat())

    def test_weekends_and_market_specific_holidays(self):
        for market, day in (
            ('GPW', '2026-11-08'), ('USA', '2026-11-08'),
            ('GPW', '2026-11-11'), ('USA', '2026-11-26'),
        ):
            with self.subTest(market=market, day=day):
                self.assertIsNone(report_window(market, at(day+'T21:10Z')))

    def test_us_early_close_uses_shortened_session(self):
        due=at('2026-11-27T18:05Z')
        self.assertIsNone(report_window('USA', due-timedelta(seconds=1)))
        window=report_window('USA', due)
        self.assertEqual(window['session_close'], at('2026-11-27T18:00Z').isoformat())
        self.assertIsNone(report_window('USA', at('2026-11-27T21:05Z')))

    def test_slow_cycle_has_a_bounded_completion_window(self):
        self.assertIsNotNone(report_window('GPW', at('2026-11-09T17:30Z')))
        self.assertIsNone(report_window('GPW', at('2026-11-09T17:30:01Z')))

    def test_naive_time_is_rejected(self):
        with self.assertRaises(ValueError):
            report_window('GPW', datetime(2026,11,9,17,10))


class ReportQueueTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store=KI.Store(Path(self.temp.name)/'reports.sqlite3')
        with self.store.transaction() as db:
            db.execute('INSERT INTO observations(ticker,interval,candle_time,acquired_at,candle_status,payload) VALUES(?,?,?,?,?,?)',
                       ('TEST','1h','2026-11-09T20:30:00+00:00','2026-11-09T21:00:00+00:00','CLOSED',
                        KI.json_text({'price':11.,'ohlc':{'open':10.},'currency':'USD','volume':100.})))

    def call_at(self, function, now):
        current=at(now)
        class Clock(datetime):
            @classmethod
            def now(cls, tz=None):
                return current.astimezone(tz) if tz else current.replace(tzinfo=None)
        with patch.object(KI, 'datetime', Clock):
            return function(self.store)

    def test_both_reporters_queue_once_after_close_only(self):
        for function, early, due, identifier in (
            (KI.daily_report_send,'2026-11-09T15:10Z','2026-11-09T16:10Z','daily_report:2026-11-09'),
            (KI.us_report_send,'2026-11-09T20:10Z','2026-11-09T21:10Z','us_report:2026-11-09'),
        ):
            with self.subTest(identifier=identifier):
                self.assertFalse(self.call_at(function,early))
                with self.store.connection() as db:
                    self.assertIsNone(db.execute('SELECT id FROM outbox WHERE id=?',(identifier,)).fetchone())
                self.assertTrue(self.call_at(function,due))
                self.assertFalse(self.call_at(function,due))
                with self.store.connection() as db:
                    rows=db.execute('SELECT status FROM outbox WHERE id=?',(identifier,)).fetchall()
                self.assertEqual([r[0] for r in rows],['PENDING'])

    def test_existing_sent_markers_prevent_resending_early_reports(self):
        with self.store.transaction() as db:
            for key in ('last_daily_report','last_us_report'):
                db.execute('INSERT INTO settings VALUES(?,?)',(key,KI.json_text('2026-11-09')))
        self.assertFalse(self.call_at(KI.daily_report_send,'2026-11-09T16:10Z'))
        self.assertFalse(self.call_at(KI.us_report_send,'2026-11-09T21:10Z'))
        with self.store.connection() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM outbox').fetchone()[0],0)


if __name__=='__main__':
    unittest.main()
