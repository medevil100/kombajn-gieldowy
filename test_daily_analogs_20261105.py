import copy
from datetime import datetime, timedelta, timezone
import json
import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import KI
import daily_analogs as daily


NOW = datetime(2026, 11, 5, 18, tzinfo=timezone.utc)


def history(ticker='TEST', count=360):
    calendar = daily.calendar_for(ticker.endswith('.WA'))
    last = daily.last_session(ticker, NOW)
    sessions = calendar.sessions_window(last, -count)
    rows = []
    for i, day in enumerate(sessions):
        close = 10. + i * .015 + math.sin(i * .2) * .03
        rows.append({'session': day.date().isoformat(), 'time': calendar.session_open(day).isoformat(),
                     'end': calendar.session_close(day).isoformat(), 'status': 'CLOSED',
                     'open': close - .01, 'high': close + .05, 'low': close - .05,
                     'close': close, 'volume': 1000. + i % 11 * 10})
    return {'version': daily.VERSION, 'ticker': ticker, 'currency': 'PLN' if ticker.endswith('.WA') else 'USD',
            'rows': rows, 'splits': [], 'rejected_count': 0, 'fetched_at': NOW.isoformat()}


def response(cache):
    return {'chart': {'error': None, 'result': [{
        'meta': {'symbol': cache['ticker'], 'currency': cache['currency'],
                 'exchangeTimezoneName': str(daily.zone(cache['ticker']))},
        'timestamp': [int(datetime.fromisoformat(row['time']).timestamp()) for row in cache['rows']],
        'indicators': {'quote': [{k: [row[k] for row in cache['rows']]
                                 for k in ('open', 'high', 'low', 'close', 'volume')}]},
    }]}}


class DailyAnalogsTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.store = KI.Store(Path(folder.name) / 'daily.sqlite3')

    def test_parser_validates_identity_ohlcv_and_official_closes(self):
        cache = history(count=80)
        raw = response(cache)
        split_time = raw['chart']['result'][0]['timestamp'][20]
        raw['chart']['result'][0]['events'] = {'splits': {'split': {'date': split_time}}}
        raw['chart']['result'][0]['indicators']['quote'][0]['open'][10] = None
        parsed = daily.parse_response(raw, 'TEST', NOW)
        self.assertEqual(parsed['rejected_count'], 1)
        self.assertEqual(len(parsed['rows']), 79)
        self.assertEqual(parsed['splits'], [cache['rows'][20]['session']])
        self.assertTrue(all(datetime.fromisoformat(r['end']) <= NOW for r in parsed['rows']))
        raw['chart']['result'][0]['meta']['symbol'] = 'OTHER'
        with self.assertRaisesRegex(ValueError, 'zgodności'):
            daily.parse_response(raw, 'TEST', NOW)

    def test_parser_skips_current_open_session_and_rejects_duplicates(self):
        cache = history(count=80)
        raw = response(cache)
        source = raw['chart']['result'][0]
        source['timestamp'].append(int(datetime(2026, 11, 5, 14, 30, tzinfo=timezone.utc).timestamp()))
        for values in source['indicators']['quote'][0].values():
            values.append(values[-1])
        parsed = daily.parse_response(raw, 'TEST', NOW)
        self.assertEqual(parsed['rows'][-1]['session'], '2026-11-04')
        source['timestamp'][-1] = source['timestamp'][0]
        with self.assertRaisesRegex(ValueError, 'powtórzoną'):
            daily.parse_response(raw, 'TEST', NOW)

    def test_last_closed_session_respects_us_half_day_and_thanksgiving(self):
        self.assertEqual(daily.last_session('TEST', datetime(2026, 11, 27, 17, 59, tzinfo=timezone.utc)), '2026-11-25')
        self.assertEqual(daily.last_session('TEST', datetime(2026, 11, 27, 18, tzinfo=timezone.utc)), '2026-11-27')

    def test_52_week_window_uses_extra_warmup_and_price_only_session_returns(self):
        cache = history()
        before = copy.deepcopy(cache)
        cases = daily.build_cases(cache, NOW)
        cutoff = (NOW.date() - timedelta(weeks=52)).isoformat()
        self.assertGreater(len(cases), 200)
        self.assertTrue(all(c['session'] >= cutoff for c in cases))
        self.assertEqual(cache, before)
        first = cases[0]
        row = first['outcomes'][5]
        target = next(r for r in cache['rows'] if r['session'] == row['session'])
        self.assertAlmostEqual(row['change'], (target['close'] / first['price'] - 1) * 100)
        self.assertIsNone(cases[-1]['outcomes'][1]['change'])

    def test_no_future_bars_or_outcomes_can_change_matching(self):
        cache = history()
        cases = daily.build_cases(cache, NOW)
        reference = cases[-15]
        earlier = daily.build_cases(cache, datetime.fromisoformat(reference['at']))
        earlier_ref = next(c for c in earlier if c['session'] == reference['session'])
        self.assertEqual(reference['features'], earlier_ref['features'])
        before = daily.find_matches(reference, cases)
        for case in cases:
            case['outcomes'][1]['change'] = 9999.
        after = daily.find_matches(reference, cases)
        self.assertEqual([(r['case']['session'], r['distance']) for r in before],
                         [(r['case']['session'], r['distance']) for r in after])
        self.assertTrue(all(item['case']['session'] < reference['session'] for item in after))

    def test_missing_session_restarts_warmup_and_is_not_shifted_in_outcomes(self):
        cache = history()
        missing_index = len(cache['rows']) - 80
        before_gap = cache['rows'][missing_index - 1]['session']
        expected_missing = cache['rows'][missing_index]['session']
        after_20 = cache['rows'][missing_index + 20]['session']
        del cache['rows'][missing_index]
        cases = daily.build_cases(cache, NOW)
        by_day = {c['session']: c for c in cases}
        self.assertNotIn(after_20, by_day)
        outcome = by_day[before_gap]['outcomes'][1]
        self.assertEqual(outcome['session'], expected_missing)
        self.assertEqual(outcome['status'], 'Brak danych z sesji')

    def test_split_excludes_crossing_returns_and_restarts_warmup(self):
        cache = history()
        index = len(cache['rows']) - 75
        day = cache['rows'][index]['session']
        cache['splits'] = [day]
        cases = {c['session']: c for c in daily.build_cases(cache, NOW)}
        before_split = cache['rows'][index - 1]['session']
        self.assertEqual(cases[before_split]['outcomes'][1]['status'], 'Split w okresie — pominięto')
        self.assertNotIn(day, cases)
        self.assertNotIn(cache['rows'][index + 20]['session'], cases)
        self.assertIn(cache['rows'][index + 65]['session'], cases)

    def test_success_is_cached_across_restart_and_does_not_write_scanner_state(self):
        cache = history()
        with patch.object(daily, 'download', return_value=cache) as fetch:
            self.assertEqual(daily.refresh(self.store, 'TEST', NOW), 'UPDATED')
            self.assertEqual(daily.refresh(KI.Store(self.store.path), 'TEST', NOW + timedelta(minutes=20)), 'CACHED')
            fetch.assert_called_once()
        with self.store.connection() as db:
            for table in ('signal_confirmations', 'observations', 'daily_candles', 'events', 'analysis_jobs', 'outbox', 'watchlist'):
                self.assertEqual(db.execute('SELECT COUNT(*) FROM ' + table).fetchone()[0], 0)
        self.assertEqual(daily.read_cache(self.store, 'TEST')['rows'], cache['rows'])

    def test_failure_preserves_last_good_data_and_durable_cooldown(self):
        cache = history()
        cache.update(checked_for_session='2026-11-03')
        with self.store.connection() as db:
            daily.write_value(db, 'daily_analog:TEST', cache, NOW)
        with patch.object(daily, 'download', side_effect=ValueError('Brak poprawnych danych')) as fetch:
            self.assertEqual(daily.refresh(self.store, 'TEST', NOW), 'FAILED')
            self.assertEqual(daily.refresh(KI.Store(self.store.path), 'TEST', NOW + timedelta(minutes=1)), 'WAIT')
            fetch.assert_called_once()
        stored = daily.read_cache(self.store, 'TEST')
        self.assertEqual(stored['rows'], cache['rows'])
        self.assertEqual(stored['fetched_at'], cache['fetched_at'])
        self.assertIn('Brak poprawnych', stored['last_error'])

    def test_rate_limit_defers_other_tickers_and_invalid_ticker_never_calls_yahoo(self):
        with patch.object(daily, 'download', side_effect=daily.YahooRateLimited('Limit')) as fetch:
            self.assertEqual(daily.refresh(self.store, 'TEST', NOW), 'FAILED')
            self.assertEqual(daily.refresh(self.store, 'OTHER', NOW + timedelta(minutes=30)), 'WAIT')
            with self.assertRaises(ValueError):
                daily.refresh(self.store, '../bad', NOW)
            fetch.assert_called_once()

    def test_future_results_are_censored_in_cards_and_labels_are_escaped(self):
        cases = daily.build_cases(history(), NOW)
        reference, old = cases[-1], cases[-2]
        self.assertIsNone(daily.visible_result(old, 5, reference)['change'])
        old['ticker'] = '<script>'
        html = daily.matches_html(reference, [{'case': old, 'distance': 0.}])
        self.assertNotIn('<script>', html)
        self.assertIn('&lt;script&gt;', html)
        self.assertIn('RVOL pełnej sesji', html)
        self.assertNotIn('1h:', html)

    def test_ui_import_is_explicit_and_refresh_does_not_call_provider(self):
        from streamlit.testing.v1 import AppTest
        cache = history()
        with self.store.connection() as db:
            daily.write_value(db, 'daily_analog:TEST', cache, NOW)
        code = ('from pathlib import Path\nimport KI, daily_analogs\n'
                f'daily_analogs.render(KI.Store(Path({str(self.store.path)!r})))')
        class FixedDate(datetime):
            @classmethod
            def now(cls, tz=None):
                return NOW if tz else NOW.replace(tzinfo=None)
        with patch.object(daily, 'refresh', return_value='CACHED') as refresh, patch.object(daily, 'datetime', FixedDate):
            app = AppTest.from_string(code).run(timeout=30)
            self.assertEqual(len(app.exception), 0)
            self.assertEqual(app.text_input(key='daily_analog_input').value, '')

            refresh.assert_not_called()
            app.text_input(key='daily_analog_input').set_value(' test ')
            next(b for b in app.button if b.label == 'Pokaż porównanie okresu').click().run(timeout=30)
            self.assertEqual(len(app.exception), 0)
            refresh.assert_called_once_with(unittest.mock.ANY, 'TEST')
            app.run(timeout=30)
            refresh.assert_called_once()
            self.assertEqual(len(app.date_input), 1)
            self.assertEqual(len(app.selectbox), 0)
            self.assertTrue(any('miesiąc po miesiącu' in x.value for x in app.subheader))
            next(b for b in app.button if b.label == 'Wyczyść').click().run(timeout=30)
            self.assertEqual(len(app.exception), 0)
            self.assertEqual(app.text_input(key='daily_analog_input').value, '')

    def test_daily_view_is_available_without_hourly_confirmations(self):
        from streamlit.testing.v1 import AppTest
        script = ('from pathlib import Path\nimport streamlit as st\nimport KI, signal_comparison\n'
                  "st.session_state.setdefault('signal_comparison_view', 'Analogie dzienne Yahoo')\n"
                  f'signal_comparison.render(KI.Store(Path({str(self.store.path)!r})))')
        with patch.object(KI, 'signal_session_outcomes', side_effect=AssertionError('Daily view must be independent')):
            app = AppTest.from_string(script).run(timeout=30)
            self.assertEqual(len(app.exception), 0)
            self.assertEqual(app.text_input(key='daily_analog_input').value, '')


if __name__ == '__main__':
    unittest.main()
