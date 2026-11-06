import copy
from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import KI
import scenario_plan
import technical_events as events
from signal_setups import compose
from technical_config import DEFAULT_CONFIG, TechnicalConfig
from test_technical_events_20261105 import snapshot as breakout


def market(prices, volumes=None):
    start = datetime(2026, 10, 26, 8, tzinfo=timezone.utc)
    rows = [dict(time=(start+timedelta(hours=i)).isoformat(), end=(start+timedelta(hours=i+1)).isoformat(),
                 open=p+.1, high=p+.2, low=p-.2, close=p,
                 volume=(volumes or [1000.]*len(prices))[i], status='CLOSED') for i, p in enumerate(prices)]
    result = KI.opportunity_test_snapshot(start+timedelta(hours=len(rows)), 'TEST', price=prices[-1])
    result.update(interval='1h', acquired_at=rows[-1]['end'], currency='USD', chart_history=KI.build_chart_history(rows))
    return result


def divergence(direction='UP'):
    prices = [100.+(i % 5)*.1 for i in range(50)] + [99, 95, 90, 85, 80, 85, 90, 100, 110]
    prices += [108-2*i for i in range(15)] + [79, 82, 85, 90]
    volume = [1000.]*len(prices)
    volume[55:59] = [5000.]*4
    volume[59:-4] = [100.]*(len(prices)-63)
    return market(prices if direction == 'UP' else [200-p for p in prices], volume)


class TechnicalExpansionTests(unittest.TestCase):
    def test_confirmed_rsi_and_obv_divergence_in_both_directions(self):
        for direction in ('UP', 'DOWN'):
            snap = divergence(direction)
            before = copy.deepcopy(snap)
            context = events.analyze(snap)
            selected = [e for e in context['events'] if 'DIVERGENCE' in e['code']]
            self.assertEqual({e['code'] for e in selected}, {'RSI_DIVERGENCE_'+direction, 'OBV_DIVERGENCE_'+direction})
            self.assertTrue(all(e['role'] == 'WARNING' and e['known_at'] == snap['chart_history'][-1]['end'] for e in selected))
            self.assertTrue(all(e['data']['right_confirmation_bars'] == 3 for e in selected))
            self.assertEqual(before, snap)
            json.dumps(context, allow_nan=False)

    def test_pivot_requires_all_right_confirmation_bars_and_does_not_repaint(self):
        snap = divergence()
        early = copy.deepcopy(snap)
        early['chart_history'] = early['chart_history'][:-1]
        early['acquired_at'] = early['chart_history'][-1]['end']
        self.assertFalse(any('DIVERGENCE' in e['code'] for e in events.analyze(early)['events']))
        expected = events.analyze(snap)
        future = copy.deepcopy(snap['chart_history'][-1])
        future.update(time=snap['acquired_at'], end=(datetime.fromisoformat(snap['acquired_at'])+timedelta(hours=1)).isoformat(),
                      open=999., close=999., high=1000., low=998.)
        snap['chart_history'].append(future)
        self.assertEqual(events.analyze(snap), expected)

    def test_carried_or_zero_volume_bar_breaks_advanced_confirmation_window(self):
        for changes in ({'price_origin': 'carried_previous_close'}, {'volume': 0}, {'close': None}):
            snap = divergence()
            snap['chart_history'][-10].update(changes)
            context = events.analyze(snap)
            self.assertFalse(any('DIVERGENCE' in e['code'] for e in context['events']))
            self.assertEqual(context['scenario']['status'], 'UNAVAILABLE')

    def test_structure_change_is_emitted_only_at_new_pivot_confirmation(self):
        points = {0:104., 29:105., 30:110., 36:100., 42:108., 48:98., 54:116., 60:103., 63:110.}
        prices = []
        for i in range(64):
            left, right = max(k for k in points if k <= i), min(k for k in points if k >= i)
            prices.append(points[left] if left == right else points[left]+(points[right]-points[left])*(i-left)/(right-left))
        for side, values in [('UP', prices), ('DOWN', [220-p for p in prices])]:
            self.assertIn('STRUCTURE_'+side, {e['code'] for e in events.analyze(market(values))['events']})
            self.assertNotIn('STRUCTURE_'+side, {e['code'] for e in events.analyze(market(values+[values[-1]+.1]))['events']})

    def test_volume_event_uses_complete_closed_periods_only(self):
        snap = breakout()
        snap['chart_history'][-1]['volume'] = 3000.
        self.assertIn('VOLUME_SURGE', {e['code'] for e in events.analyze(snap)['events']})
        snap['chart_history'][-1]['end'] = (datetime.fromisoformat(snap['chart_history'][-1]['time'])+timedelta(minutes=30)).isoformat()
        self.assertNotIn('VOLUME_SURGE', {e['code'] for e in events.analyze(snap)['events']})

    def test_setups_need_three_families_and_never_add_score(self):
        snap = breakout()
        snap['chart_history'][-1]['volume'] = 3000.
        original = copy.deepcopy(snap)
        context = events.analyze(snap)
        self.assertEqual(len(context['setups']), 1)
        setup = context['setups'][0]
        self.assertEqual(setup['families'], ['PRICE', 'MOMENTUM', 'ACTIVITY'])
        self.assertEqual(setup['score_effect'], 0)
        self.assertEqual(len(setup['components']), 3)
        self.assertEqual(setup['id'], events.analyze(snap)['setups'][0]['id'])
        self.assertEqual(snap, original)
        no_flow = [e for e in context['events'] if e['code'] != 'VOLUME_SURGE' and e.get('kind') != 'COMPOSITE']
        self.assertEqual(compose(snap, no_flow, DEFAULT_CONFIG), [])

    def test_setups_surface_conflicts_and_reject_mixed_candle_times(self):
        snap = breakout()
        snap['chart_history'][-1]['volume'] = 3000.
        context = events.analyze(snap)
        atomic = [e for e in context['events'] if e.get('kind') != 'COMPOSITE']
        warning = {**atomic[0], 'code': 'RSI_DIVERGENCE_DOWN', 'direction': 'DOWN', 'role': 'WARNING'}
        setup = compose(snap, atomic+[warning], DEFAULT_CONFIG)[0]
        self.assertIn('RSI_DIVERGENCE_DOWN', setup['conflicts'])
        self.assertEqual(setup['role'], 'WARNING')
        for event in atomic:
            if event['code'] == 'VOLUME_SURGE': event['candle_time'] = '2026-01-01T00:00:00Z'
        self.assertEqual(compose(snap, atomic, DEFAULT_CONFIG), [])

    def test_scenarios_have_exact_complementary_guards_and_no_execution_claim(self):
        for prices, direction, operator in [([100+.01*i*i for i in range(60)], 'UP', 'LE'),
                                             ([200-.01*i*i for i in range(60)], 'DOWN', 'GE')]:
            snap = market(prices)
            plan = events.analyze(snap)['scenario']
            self.assertEqual((plan['status'], plan['direction']), ('CONDITIONAL', direction))
            self.assertEqual(plan['invalidation']['operator'], operator)
            self.assertEqual(plan['condition']['level'], plan['invalidation']['level'])
            self.assertFalse(plan['execution_confirmed'])
            self.assertFalse(plan['is_trade_plan'])
            self.assertIn('zamknię', plan['alternative'].lower())
            self.assertIn('condition', plan)

    def test_scenario_is_unavailable_for_missing_history_and_historical_after_expiry(self):
        snap = breakout()
        rows = snap['chart_history']
        self.assertEqual(scenario_plan.build(snap, rows[:10], [])['status'], 'UNAVAILABLE')
        old = {**snap, 'acquired_at': (datetime.fromisoformat(snap['acquired_at'])+timedelta(hours=2)).isoformat()}
        self.assertEqual(scenario_plan.build(old, rows, [])['status'], 'HISTORICAL')
        with_future = rows + [{**rows[-1], 'time': snap['acquired_at'],
                              'end': (datetime.fromisoformat(snap['acquired_at'])+timedelta(hours=1)).isoformat()}]
        self.assertEqual(scenario_plan.build(snap, with_future, []), scenario_plan.build(snap, rows, []))

    def test_range_scenario_and_config_validation(self):
        snap = market([100.+(i % 2) for i in range(60)])
        plan = events.analyze(snap)['scenario']
        self.assertEqual(plan['direction'], 'RANGE')
        self.assertEqual(plan['invalidation']['operator'], 'OUTSIDE')
        for changes in ({'pivot_width': True}, {'sma_fast': 40, 'sma_slow': 30},
                        {'closed_volume_ratio': float('inf')}, {'doji_fraction': 2}):
            with self.assertRaises(ValueError): TechnicalConfig(**changes)
        with self.assertRaises(FrozenInstanceError): DEFAULT_CONFIG.pivot_width = 2
        changed = replace(DEFAULT_CONFIG, rsi_divergence_points=90.)
        self.assertNotEqual(changed.identifier, DEFAULT_CONFIG.identifier)
        self.assertNotIn('RSI_DIVERGENCE_UP', {e['code'] for e in events.analyze(divergence(), changed)['events']})

    def test_ai_manifest_gets_local_rules_events_and_scenarios_without_calls(self):
        snap = breakout()
        snap['chart_history'][-1]['volume'] = 3000.
        evidence = {'kind': 'CONFIRMED_OPPORTUNITY', 'snapshot': snap, 'autonomous_assessment_version': 1}
        context = {'sources': []}
        with patch.object(KI, 'fetch_market', side_effect=AssertionError('No provider requests')):
            manifest = KI.build_analysis_manifest(evidence, context)
            self.assertEqual(manifest['technical_events']['config_id'], DEFAULT_CONFIG.identifier)
            self.assertEqual(manifest['scenario_plan']['status'], 'CONDITIONAL')
            context.update(analysis_manifest=manifest, ai_preflight=KI.automatic_ai_preflight(evidence, context))
            request = KI.event_analysis_request(evidence, context)
        package = json.loads(request['messages'][-1]['content'])['proved_event']['analysis_manifest']
        self.assertEqual(package['scenario_plan'], manifest['scenario_plan'])
        self.assertEqual(package['technical_events'], manifest['technical_events'])
        self.assertIn('nie zwiększa punktacji', request['messages'][0]['content'])
        self.assertIn('Nie zmieniaj jego poziomów', request['messages'][0]['content'])

    def test_new_composite_is_saved_once_for_session_outcomes(self):
        snap = breakout()
        snap['chart_history'][-1]['volume'] = 3000.
        matrix = {'newly_confirmed': True, 'activity_verified': True, 'change_pct': 9., 'state': 'CONFIRMED'}
        with tempfile.TemporaryDirectory() as folder:
            store = KI.Store(Path(folder) / 'expansion.sqlite3')
            with patch.object(KI, '_record_price_matrix_read', return_value=matrix):
                KI.detect_market(store, snap, {'price_matrix_enabled': True})
                with store.connection() as db:
                    before = db.execute('SELECT payload FROM signal_technical_context').fetchone()[0]
                KI.detect_market(store, {**snap, 'chart_history': []}, {'price_matrix_enabled': True})
            with store.connection() as db:
                after = db.execute('SELECT payload FROM signal_technical_context').fetchone()[0]
                self.assertEqual(before, after)
                self.assertEqual(db.execute('SELECT COUNT(*) FROM signal_technical_context').fetchone()[0], 1)
            context = json.loads(after)
            self.assertIn('SETUP_BREAKOUT_UP', {e['code'] for e in context['events']})
            self.assertEqual(context['config_id'], DEFAULT_CONFIG.identifier)
            rows = KI.signal_session_outcomes(store, '2026-11-05T18:00:00+00:00')
            self.assertTrue(all('SETUP_BREAKOUT_UP' in {e['code'] for e in r['technical_events']['events']} for r in rows))
            from signal_comparison import cases_from_rows, event_statistics
            statistics = event_statistics(cases_from_rows(rows), 1)
            group = next(r for r in statistics if r['code'] == 'SETUP_BREAKOUT_UP')
            self.assertEqual(group['total'], 1)

    def test_mobile_cards_keep_three_chips_and_escape_scenario_text(self):
        view = events.analyze(divergence())
        view['scenario']['alternative'] = '<script>danger</script>'
        with patch.object(scenario_plan, 'datetime') as clock:
            clock.now.return_value = datetime(2026, 11, 6, tzinfo=timezone.utc)
            html = events.cards_html(view)
        self.assertIn('Scenariusze warunkowe', html)
        self.assertIn('zapis historyczny', html)
        self.assertIn('Alternatywa i warunek zanegowania', html)
        self.assertNotIn('<script>', html)
        self.assertIn('&lt;script&gt;', html)
        self.assertLessEqual(html.count('<span class="ki-event-chip '), 3)
        self.assertIn('min-height:44px', html)

    def test_daily_period_keeps_events_on_unchanged_price_days(self):
        import daily_analogs
        from test_daily_analogs_20261105 import history, NOW
        cache = history('HUMA')
        current, previous = cache['rows'][-2:]
        # Make the final day a true unchanged-close Doji while preserving OHLCV.
        previous.update(open=current['close'], close=current['close'],
                        low=current['close']-.05, high=current['close']+.05)
        old = daily_analogs.build_cases(cache, NOW)
        timeline = daily_analogs.build_cases(cache, NOW, require_features=False)
        self.assertNotIn(previous['session'], {c['session'] for c in old})
        case = next(c for c in timeline if c['session'] == previous['session'])
        self.assertIsNone(case['features'])
        self.assertIn('DOJI', {e['code'] for e in case['events']})
        self.assertEqual(case['config_id'], DEFAULT_CONFIG.identifier)


if __name__ == '__main__':
    unittest.main()
