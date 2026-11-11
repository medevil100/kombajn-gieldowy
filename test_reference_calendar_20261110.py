"""One exchange calendar for source scheduling, daily base and signal eligibility."""
from datetime import datetime,timezone
from pathlib import Path
import tempfile
import unittest
import KI


def at(value):return datetime.fromisoformat(value.replace('Z','+00:00'))


class ReferenceCalendarTests(unittest.TestCase):
    def test_gpw_reference_after_november_holiday_is_last_real_session(self):
        self.assertEqual(KI.required_daily_session('STX.WA','2026-11-12T08:30:00Z'),'2026-11-10')
        self.assertEqual(KI.required_daily_session('STX.WA','2026-11-11T12:00:00Z',True),'2026-11-10')

    def test_closed_exchange_does_not_count_as_live_market(self):
        self.assertFalse(KI.automatic_session_open('STX.WA','2026-11-11T10:00:00Z'))
        self.assertTrue(KI.automatic_session_open('STX.WA','2026-11-12T10:00:00Z'))
        self.assertFalse(KI.market_session_open('TEST','2026-11-26T16:00:00Z'))

    def test_next_open_skips_market_holidays(self):
        self.assertEqual(KI.next_market_open('STX.WA','2026-11-10T20:00:00Z'),at('2026-11-12T08:00:00Z'))
        self.assertEqual(KI.next_market_open('TEST','2026-11-25T22:00:00Z'),at('2026-11-27T14:30:00Z'))

    def test_us_early_close_is_shared_by_reference_and_market_session(self):
        self.assertTrue(KI.market_session_open('TEST','2026-11-27T17:59:59Z'))
        self.assertFalse(KI.market_session_open('TEST','2026-11-27T18:00:00Z'))
        self.assertEqual(KI.required_daily_session('TEST','2026-11-27T18:01:00Z',True),'2026-11-27')
        self.assertEqual(KI._daily_session_end('TEST','2026-11-27'),at('2026-11-27T18:00:00Z'))

    def test_old_non_session_row_cannot_replace_the_real_daily_reference(self):
        with tempfile.TemporaryDirectory() as folder:
            store=KI.Store(Path(folder)/'calendar.sqlite3')
            with store.transaction() as db:
                for day,close in (('2026-11-10',1.948),('2026-11-11',999.)):
                    db.execute('INSERT INTO daily_candles VALUES(?,?,?,?,?,?,?,?,?,?)',
                        ('STX.WA',day,close,close,close,close,100.,day+'T17:00:00+01:00','fixture','{}'))
            with store.connection() as db:reference=KI._daily_reference(db,'STX.WA','2026-11-12T08:00:00Z')
            self.assertEqual((reference['session_date'],reference['close']),('2026-11-10',1.948))

    def test_closed_day_refresh_check_does_not_invent_a_daily_candle(self):
        with tempfile.TemporaryDirectory() as folder:
            store=KI.Store(Path(folder)/'calendar.sqlite3')
            KI._save_daily_history(store,'STX.WA',[{'session_date':'2026-11-10','status':'CLOSED',
                'open':2.,'high':2.,'low':2.,'close':2.,'volume':100.}],at('2026-11-10T18:00:00Z'))
            self.assertFalse(KI.daily_history_refresh_due(store,'STX.WA','2026-11-11T10:00:00Z'))
            with self.assertRaises(ValueError):
                KI._save_daily_history(store,'STX.WA',[{'session_date':'2026-11-11','status':'CLOSED',
                    'open':2.,'high':2.,'low':2.,'close':2.,'volume':100.,'end':'2026-11-11T17:00:00+01:00'}],at('2026-11-12T08:00:00Z'))


if __name__=='__main__':unittest.main()
