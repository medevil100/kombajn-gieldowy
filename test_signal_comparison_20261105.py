import copy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import KI
import signal_comparison as comparison


def snapshot():
    start = datetime(2026, 10, 26, 8, tzinfo=timezone.utc)
    bars = [{'time': (start + timedelta(hours=i)).isoformat(),
             'end': (start + timedelta(hours=i + 1)).isoformat(),
             'open': 100., 'high': 101., 'low': 99., 'close': 100.,
             'volume': 1000., 'status': 'CLOSED'} for i in range(60)]
    bars[-1].update(open=100., high=122., low=100., close=120.)
    result = KI.opportunity_test_snapshot(start + timedelta(hours=60), 'AAA', price=120.)
    return {**result, 'currency': 'USD', 'chart_history': KI.build_chart_history(bars)}


def feature(at='2026-11-02T10:00:00+00:00', **changes):
    time = datetime.fromisoformat(at)
    return {'version': comparison.VERSION, 'interval': '1h',
            'candle_time': (time - timedelta(hours=2)).isoformat(),
            'candle_end': (time - timedelta(hours=1)).isoformat(),
            'movement_pct': 5., 'closed_rvol': 2., 'sma_gap_pct': 1.,
            'price_sma10_pct': 2., 'macd_hist_pct': .1, **changes}


def case(ticker='OLD', at='2026-11-02T10:00:00+00:00', direction='Wzrost', **changes):
    return {'ticker': ticker, 'confirmed_at': at, 'direction': direction,
            'currency': 'PLN' if ticker.endswith('.WA') else 'USD', 'price': 10.,
            'events': {'SMA_CROSS_UP': 'Przecięcie SMA w górę'},
            'features': feature(at), 'outcomes': {}, **changes}


def result(change=10., status='Obliczono', close='2026-11-03T21:00:00+00:00'):
    return {'change': change, 'status': status, 'session_close': close,
            'candle': {'closed_at': close}}


def outcome_rows(cases):
    return [{**{k: c[k] for k in ('ticker', 'confirmed_at', 'direction', 'currency', 'price')},
             'horizon': horizon, 'technical_events': {'events': [{'code': k, 'label': v} for k, v in c['events'].items()],
                                                     'comparison': c['features']},
             **c['outcomes'].get(horizon, result(None, 'Oczekuje na zamknięcie'))}
            for c in cases for horizon in comparison.HORIZONS]


class SignalComparisonTests(unittest.TestCase):
    def test_features_use_only_closed_bars_and_do_not_change_snapshot(self):
        current = snapshot()
        current['chart_history'][-1]['status'] = 'OPEN'
        current['chart_history'][-1]['volume'] = 99999999
        before = copy.deepcopy(current)
        f = comparison.features(current, 5.)
        self.assertAlmostEqual(f['closed_rvol'], 1.)
        self.assertEqual(f['candle_time'], current['chart_history'][-2]['time'])
        self.assertEqual(current, before)
        current['chart_history'][-10]['price_origin'] = 'carried_previous_close'
        self.assertIsNone(comparison.features(current, 5.))

    def test_statistics_count_each_issuer_session_type_once_and_preserve_denominators(self):
        first = case(outcomes={1: result(10.)})
        duplicate = case(at='2026-11-02T11:00:00+00:00', outcomes={1: result(50.)})
        missing = case('MISSING', outcomes={1: result(None, 'Brak danych z sesji')})
        pending = case('PENDING', outcomes={1: result(None, 'Oczekuje na zamknięcie')})
        flat = case('FLAT', outcomes={1: result(0.)})
        first['events']['RESISTANCE_BREAKOUT'] = 'Wybicie oporu'
        rows = comparison.event_statistics([first, duplicate, missing, pending, flat], 1)
        row = next(r for r in rows if r['code'] == 'SMA_CROSS_UP')
        self.assertEqual((row['total'], row['n'], row['continued'], row['flat'], row['missing'], row['pending']), (4, 2, 1, 1, 1, 1))
        self.assertEqual((row['mean'], row['median']), (5., 5.))
        self.assertEqual(next(r for r in rows if r['code'] == 'RESISTANCE_BREAKOUT')['n'], 1)

    def test_nonfinite_derived_feature_cannot_be_saved_to_scanner_payload(self):
        current = snapshot()
        for bar in current['chart_history']:
            bar['volume'] = 1e-300
        current['chart_history'][-1]['volume'] = 1e300
        self.assertIsNone(comparison.features(current, 5.))

    def test_downward_statistics_use_negative_returns_and_markets_are_separate(self):
        rows = comparison.event_statistics([case(direction='Spadek', outcomes={1: result(-10.)}),
                                            case('GPW.WA', direction='Spadek', outcomes={1: result(20.)})], 1)
        usa = next(r for r in rows if r['market'] == 'USA')
        gpw = next(r for r in rows if r['market'] == 'GPW')
        self.assertEqual((usa['continued'], usa['mean']), (1, -10.))
        self.assertEqual((gpw['continued'], gpw['mean']), (0, 20.))

    def test_matching_excludes_future_other_market_direction_and_incomplete_features(self):
        reference = case('REFERENCE', '2026-11-05T15:00:00+00:00')
        good = case('REFERENCE')
        wrong = [case('FOREIGN'), case('FUTURE', '2026-11-06T15:00:00+00:00'), case('OTHER.WA'),
                 case('DOWN', direction='Spadek'), case('EMPTY', features=None),
                 case('VOLUME', features=feature(closed_rvol=20.)),
                 case('MACD', features=feature(macd_hist_pct=-.1)),
                 case('FUTUREBAR', features=feature(candle_end='2026-11-06T15:00:00+00:00'))]
        found = comparison.similar_cases(reference, [good] + wrong)
        self.assertEqual([r['case']['ticker'] for r in found], ['REFERENCE'])

    def test_matching_does_not_use_outcomes_and_chooses_one_case_per_issuer_day(self):
        reference = case('REF', '2026-11-05T15:00:00+00:00')
        a, b = case('REF'), case('REF', '2026-11-03T10:00:00+00:00', features=feature(movement_pct=5.5))
        initial = comparison.similar_cases(reference, [a, b, copy.deepcopy(a)])
        a['outcomes'] = {1: result(-99.)}
        b['outcomes'] = {1: result(1000.)}
        later = comparison.similar_cases(reference, [a, b, copy.deepcopy(a)])
        self.assertEqual([r['case']['ticker'] for r in initial], ['REF', 'REF'])
        self.assertEqual(len(initial), 2)
        self.assertEqual([r['distance'] for r in initial], [r['distance'] for r in later])

    def test_historical_results_are_censored_at_reference_confirmation(self):
        old = case(outcomes={1: result(10.), 2: result(20., close='2026-11-06T21:00:00+00:00')})
        at = datetime.fromisoformat('2026-11-05T15:00:00+00:00')
        self.assertEqual(comparison.outcome_asof(old, 1, at)['change'], 10.)
        self.assertEqual(comparison.outcome_asof(old, 2, at)['change'], None)
        old['outcomes'][1]['candle']['closed_at'] = '2026-11-06T21:00:00+00:00'
        self.assertEqual(comparison.outcome_asof(old, 1, at)['status'], 'Brak danych z sesji')

    def test_original_feature_recovery_cannot_substitute_later_observation(self):
        with tempfile.TemporaryDirectory() as folder:
            store = KI.Store(Path(folder) / 'cases.sqlite3')
            original = snapshot()
            original['price_matrix'] = {'newly_confirmed': True, 'activity_verified': True, 'change_pct': 5.}
            target = case('AAA', original['acquired_at'], price=original['price'], features=None)
            with store.connection() as db:
                db.execute("INSERT INTO observations(ticker,interval,candle_time,acquired_at,candle_status,payload) VALUES('AAA','1h',?,?,'OPEN',?)",
                           (original['candle_time'], original['acquired_at'], KI.encode_observation(original)))
                before = list(db.iterdump())
            with patch.object(KI, 'fetch_market', side_effect=AssertionError('No requests')):
                comparison.recover_original_features(store, [target])
                self.assertTrue(comparison.valid_features(target['features']))
                changed = case('AAA', '2026-11-04T15:00:00+00:00', features=None)
                comparison.recover_original_features(store, [changed])
                self.assertIsNone(changed['features'])
            with store.connection() as db:
                self.assertEqual(before, list(db.iterdump()))

    def test_detector_saves_comparison_once_and_exact_session_closes_are_available(self):
        current = snapshot()
        with tempfile.TemporaryDirectory() as folder:
            store = KI.Store(Path(folder) / 'cases.sqlite3')
            matrix = {'newly_confirmed': True, 'activity_verified': True, 'change_pct': 5., 'state': 'CONFIRMED'}
            with patch.object(KI, '_record_price_matrix_read', return_value=matrix):
                KI.detect_market(store, current, {'price_matrix_enabled': True})
                KI.detect_market(store, {**current, 'chart_history': []}, {'price_matrix_enabled': True})
            rows = KI.signal_session_outcomes(store, '2026-11-05T18:00:00+00:00')
            cases = comparison.cases_from_rows(rows)
            self.assertTrue(comparison.features_at(cases[0]))
            self.assertTrue(all(r['session_close'] for r in rows))

    def test_comparison_view_starts_with_one_issuer_and_no_market_pool(self):
        from streamlit.testing.v1 import AppTest
        with tempfile.TemporaryDirectory() as folder:
            store = KI.Store(Path(folder) / 'cases.sqlite3')
            script = 'from pathlib import Path\nimport KI, signal_comparison\n' + f'signal_comparison.render(KI.Store(Path({str(store.path)!r})))'
            with patch.object(KI, 'signal_session_outcomes', side_effect=AssertionError('No pooled KI history')):
                app = AppTest.from_string(script).run(timeout=30)
                self.assertEqual(len(app.exception), 0)
                self.assertEqual(app.text_input(key='daily_analog_input').value, '')
                self.assertFalse(any(s.key == 'comparison_market' for s in app.selectbox))
                self.assertTrue(any('tej samej spółki' in s.value for s in app.subheader))

    def test_cards_escape_labels_and_remain_responsive(self):
        rows = comparison.event_statistics([case(events={'CODE': '<script>test</script>'}, outcomes={1: result(10.)})], 1)
        html = comparison.statistics_html(rows)
        self.assertNotIn('<script>', html)
        self.assertIn('&lt;script&gt;', html)
        self.assertIn('@media(max-width:640px)', html)
        reference = case('REF', '2026-11-05T15:00:00+00:00')
        html = comparison.similar_html(reference, comparison.similar_cases(reference, [case('<script>')]))
        self.assertNotIn('<script>', html)
        self.assertIn('min-height:44px', html)


if __name__ == '__main__':
    unittest.main()
