import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import KI
import portfolio_view


class SignalOutcomeTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.store = KI.Store(Path(folder.name) / 'signals.sqlite3')

    def test_original_confirmation_survives_a_later_observation(self):
        at = '2026-11-10T10:00:00+00:00'
        now = datetime.fromisoformat('2026-11-17T16:30:00+00:00')
        reading = {'price': 10., 'currency': 'PLN', 'price_matrix': {
            'newly_confirmed': True, 'activity_verified': True, 'change_pct': 3.}}
        later = {'snapshot': {'price': 20., 'price_matrix': {'confirmed_at': at}}}
        with self.store.transaction() as connection:
            connection.execute('INSERT INTO opportunities VALUES(?,?,?,?,?,?,?,?,?)',
                ('seq', 'AAA.WA', at, at, 'EXPIRED', 'cycle', json.dumps(later), at, at))
            connection.execute('''
                INSERT INTO observations(ticker,interval,candle_time,acquired_at,candle_status,payload)
                VALUES('AAA.WA','1h',?,?,'OPEN',?)
            ''', (at, at, json.dumps(reading)))
        KI._save_daily_history(self.store, 'AAA.WA', [
            {'session_date': day, 'status': 'CLOSED', 'open': 10., 'high': 12., 'low': 9.,
             'close': close, 'volume': 500.}
            for day, close in (('2026-11-12', 11.), ('2026-11-16', 9.))
        ], now)
        with self.store.connection() as connection:
            before = list(connection.iterdump())
        results = KI.signal_session_outcomes(self.store, now)
        self.assertEqual([r['session'] for r in results],
                         ['2026-11-12', '2026-11-13', '2026-11-16', '2026-11-18'])
        self.assertEqual([r['status'] for r in results], [
            'Obliczono', 'Brak danych z sesji', 'Obliczono', 'Oczekuje na zamknięcie'])
        self.assertAlmostEqual(results[0]['change'], 10.)
        self.assertAlmostEqual(results[2]['change'], -10.)
        self.assertEqual(results[0]['candle']['volume'], 500.)
        with self.store.connection() as connection:
            self.assertEqual(list(connection.iterdump()), before)
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM signal_confirmations').fetchone()[0], 0)

    def test_confirmed_read_is_saved_once_in_the_normal_detector(self):
        now = datetime.fromisoformat('2026-11-25T16:00:00+00:00')
        snapshot = KI.opportunity_test_snapshot(now, 'AAA', price=10.)
        snapshot['currency'] = 'USD'
        matrix = {'newly_confirmed': True, 'activity_verified': True, 'anchor_price': 11.,
                  'change_pct': -9., 'state': 'CONFIRMED'}
        settings = {'price_matrix_enabled': True}
        with patch.object(KI, '_record_price_matrix_read', return_value=matrix):
            KI.detect_market(self.store, snapshot, settings)
            KI.detect_market(self.store, snapshot, settings)
        with self.store.connection() as connection:
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM signal_confirmations').fetchone()[0], 1)
        pending = KI.signal_session_outcomes(self.store, '2026-11-27T17:59:59+00:00')[0]
        closed = KI.signal_session_outcomes(self.store, '2026-11-27T18:00:00+00:00')[0]
        self.assertEqual(closed['session'], '2026-11-27')
        self.assertEqual(closed['direction'], 'Spadek')
        self.assertEqual(pending['status'], 'Oczekuje na zamknięcie')
        self.assertEqual(closed['status'], 'Brak danych z sesji')


class SupplementalIndicatorTests(unittest.TestCase):
    def test_session_vwap_starts_at_opening_and_refuses_gaps(self):
        rows = [
            {'time': '2026-11-03T16:00:00+01:00', 'high': 90., 'low': 90., 'close': 90., 'volume': 100.},
            {'time': '2026-11-04T09:00:00+01:00', 'high': 12., 'low': 9., 'close': 9., 'volume': 10.},
            {'time': '2026-11-04T10:00:00+01:00', 'high': 21., 'low': 19., 'close': 20., 'volume': 30.},
        ]
        self.assertEqual(KI.session_vwap(rows, 'AAA.WA', '1h'), 17.5)
        self.assertIsNone(KI.session_vwap(rows[::2], 'AAA.WA', '1h'))
        self.assertIsNone(KI.session_vwap(rows, 'AAA.WA', '1d'))

    def test_fibonacci_uses_closed_candles_and_stoch_rsi_rejects_flat_range(self):
        start = datetime.fromisoformat('2026-09-01T00:00:00+02:00')
        rows = [{'time': (start + timedelta(days=index)).isoformat(), 'status': 'CLOSED',
                 'close': 10., 'high': 12., 'low': 8., 'volume': 1.} for index in range(35)]
        rows.append({**rows[-1], 'status': 'OPEN', 'high': 100.})
        values = KI.supplemental_market_indicators(rows, 'AAA.WA', '1d')
        self.assertEqual([values['fibonacci'][i] for i in (0, 3, 6)], [12., 10., 8.])
        self.assertIsNone(values['stoch_rsi_k'])
        self.assertIsNone(values['stoch_rsi_d'])
        snapshot = {'currency': 'PLN', 'supplemental_indicators': values}
        indicators = KI.supplemental_indicator_rows(snapshot)
        self.assertIn({'Wskaźnik': 'Fibonacci 50%', 'Wartość': '10,0000 PLN'}, indicators)
        self.assertIn('VWAP, Stoch RSI i Fibonacci',
                      portfolio_view.cards_html([{'Ticker': 'AAA.WA', '_supplemental_indicators': indicators}]))
        self.assertEqual(KI.supplemental_indicator_rows({}), [])

    def test_stoch_rsi_smooths_rsi_position_instead_of_price_position(self):
        rows = [{'close': 10.}] * 33
        rsi = [None] * 14 + [40., 60.] + [45.] * 12 + [40., 60., 50., 40., 40.]
        with patch.object(KI, 'market_rsi', return_value=rsi):
            values = KI.supplemental_market_indicators(rows, 'AAA', '1d')
        self.assertAlmostEqual(values['stoch_rsi_k'], 50 / 3)
        self.assertAlmostEqual(values['stoch_rsi_d'], 350 / 9)


if __name__ == '__main__':
    unittest.main()
