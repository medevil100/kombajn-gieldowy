"""Real SQLite pipeline and deterministic evidence contracts; no paid providers."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import KI
import analysis_verdict as av
from test_repair_20261024 import NOW


class AutonomousReviewTests(unittest.TestCase):
    def sample(self, ticker='AAA.WA'):
        snap = KI.opportunity_test_snapshot(NOW, ticker)
        snap['price_matrix'] = {'change_pct': 5., 'anchor_price': 100.,
                                'anchor_at': '2026-10-09T15:00:00Z', 'state': 'CONFIRMED'}
        ev = {'kind': 'CONFIRMED_OPPORTUNITY', 'autonomous_assessment_version': 1,
              'snapshot': snap, 'manual_analysis': True}
        ctx = {'sources': [], 'cutoff': snap['acquired_at']}
        ctx['analysis_manifest'] = KI.build_analysis_manifest(ev, ctx)
        result = {'technical': [
            {'metric': 'ma_fast', 'interpretation': 'Cena jest powyżej szybkiej średniej, co wspiera wzrost.'},
            {'metric': 'rsi', 'interpretation': 'RSI wspiera wzrostowe momentum.'}],
            'context': [], 'hypotheses': [], 'risks': [], 'missing': [],
            'assessment': {'movement': 'Wskazania są zgodne ze wzrostem.',
                           'activity': 'Wolumen trwającej świecy już przekracza średnią pełnych godzin.',
                           'risk': 'Brak ofert ogranicza ocenę ryzyka wykonania.'},
            'decision': {'verdict': 'ALIGNED', 'reason_codes': ['TECH_SUPPORT']}}
        return ev, ctx, result

    def local(self, ev):
        return KI.build_analysis_manifest(ev, {'sources': []})['local_review']

    def test_all_tickers_share_contract_and_legacy_events_keep_version_three(self):
        for ticker in ('AAA.WA', 'BRK.B', 'XYZ', '3RG.WA'):
            ev, ctx, result = self.sample(ticker)
            self.assertEqual(self.local(ev)['verdict'], 'ALIGNED')
            self.assertFalse(av.material_issues(ev['snapshot']))
            del ev['autonomous_assessment_version']
            legacy = KI.build_analysis_manifest(ev, {'sources': []})
            self.assertEqual(legacy['version'], 3)
            self.assertNotIn('local_review', legacy)
            self.assertNotIn('decision', KI.analysis_schema(ev['snapshot'], {'sources': [], 'analysis_manifest': legacy})['required'])

    def test_absent_quotes_limit_execution_without_erasing_technical_verdict(self):
        ev, ctx, result = self.sample()
        before = copy.deepcopy(ev)
        local = self.local(ev)
        self.assertEqual((local['verdict'], local['execution'], local['coverage']), ('ALIGNED', 'MISSING', 'PARTIAL'))
        self.assertEqual(ev, before)

    def test_verdict_mixed_and_opposed_are_distinct(self):
        ev, ctx, result = self.sample()
        ev['snapshot']['indicators']['last_macd_hist'] = -.1
        self.assertEqual(self.local(ev)['verdict'], 'MIXED')
        ev['snapshot']['indicators'].update(ma_fast=110, plus_di=10, minus_di=30, rsi=40)
        self.assertEqual(self.local(ev)['verdict'], 'CONTRADICTED')

    def test_unverified_wide_quotes_warn_but_do_not_prove_live_cost(self):
        ev, ctx, result = self.sample()
        q = {'bid': 100., 'ask': 110., 'freshness_confirmed': True,
             'acquired_at': ev['snapshot']['acquired_at']}
        ev['snapshot']['spread'] = q
        local = self.local(ev)
        self.assertEqual(local['verdict'], 'ALIGNED')
        self.assertEqual(local['execution'], 'UNVERIFIED')
        self.assertIn('WIDE_SPREAD', local['evidence'])
        q['quote_time'] = q['acquired_at']
        self.assertEqual(self.local(ev)['verdict'], 'RISK_DOMINANT')
        q['quote_time'] = '2026-10-12T14:31:00Z'
        self.assertEqual(self.local(ev)['execution'], 'UNVERIFIED')

    def test_spread_is_recomputed_instead_of_trusting_supplied_zero(self):
        ev, ctx, result = self.sample()
        ev['snapshot']['spread'] = {'bid': 100, 'ask': 110, 'spread_pct': 0}
        self.assertGreater(self.local(ev)['spread_pct'], 9)
        ev['snapshot']['spread'] = {'bid': 110, 'ask': 100}
        self.assertEqual(self.local(ev)['execution'], 'MISSING')

    def test_decline_is_weakened_by_bounce_not_distance_below_high(self):
        ev, ctx, result = self.sample()
        s = ev['snapshot']
        s.update(price=95., ohlc={'open': 100., 'high': 101., 'low': 95., 'close': 95.})
        s['price_matrix']['change_pct'] = -5
        self.assertNotIn('ADVERSE_RETRACE', self.local(ev)['evidence'])
        self.assertFalse(any('Cofnięcie' in x for x in KI.opportunity_risk(s)['reasons']))
        s['ohlc']['low'] = 92.
        self.assertIn('ADVERSE_RETRACE', self.local(ev)['evidence'])
        self.assertIn('Odbicie', KI.opportunity_risk(s)['reasons'][0])

    def test_poor_reward_to_risk_dominates_without_inventing_levels(self):
        ev, ctx, result = self.sample()
        manifest = copy.deepcopy(ctx['analysis_manifest'])
        manifest['trade_plan'] = {'status': 'INDICATIVE', 'rr1': .8}
        local = av.review(ev['snapshot'], manifest)
        self.assertEqual(local['verdict'], 'RISK_DOMINANT')
        self.assertIn('POOR_RR', local['required_reason_codes'])

    def test_incoherent_material_blocks_all_provider_stages(self):
        for field, value in (('volume', None), ('average_volume', 0), ('rvol', float('nan')),
                             ('price', True), ('candle_status', 'CLOSED'), ('candle_time', 'bad')):
            ev, ctx, result = self.sample()
            ev['snapshot'][field] = value
            self.assertTrue(av.material_issues(ev['snapshot']), field)
        ev, ctx, result = self.sample()
        ev['snapshot']['ohlc']['high'] = 104
        self.assertTrue(av.material_issues(ev['snapshot']))
        ev, ctx, result = self.sample()
        ev['snapshot']['indicators']['rsi'] = 150
        self.assertEqual(self.local(ev)['verdict'], 'INSUFFICIENT')

    def test_actual_worker_filters_before_research_and_ai_without_calls(self):
        with tempfile.TemporaryDirectory() as folder:
            store = KI.Store(Path(folder) / 'test.sqlite3')
            for index, state in enumerate(('PENDING_CONTEXT', 'PENDING_AI')):
                ev, ctx, result = self.sample()
                ev['snapshot']['volume'] = None
                event_id = 'e' + str(index)
                with store.transaction() as c:
                    c.execute('INSERT INTO events VALUES(?,?,?,?,?)', (event_id, 'AAA.WA', '1h', NOW.isoformat(), KI.json_text(ev)))
                    c.execute('INSERT INTO analysis_jobs(event_id,state,context,updated_at) VALUES(?,?,?,?)',
                              (event_id, state, KI.json_text(ctx), NOW.isoformat()))
                with patch.object(KI, 'submit_event_research', side_effect=AssertionError('Research forbidden')), patch.object(KI, 'analyze_event', side_effect=AssertionError('AI forbidden')):
                    self.assertTrue(KI.process_analysis_once(store, {}, event_id))
                with store.connection() as c:
                    row = c.execute('SELECT state,result FROM analysis_jobs WHERE event_id=?', (event_id,)).fetchone()
                    self.assertEqual(row['state'], 'FILTERED')
                    self.assertTrue(json.loads(row['result'])['provider']['research_not_called'])
                    self.assertEqual(c.execute('SELECT COUNT(*) FROM outbox').fetchone()[0], 0)
                    self.assertEqual(c.execute('SELECT COUNT(*) FROM research_requests').fetchone()[0], 0)

    def test_material_filter_retains_previously_collected_context(self):
        ev, ctx, result = self.sample()
        ctx['audit_note'] = 'wcześniej zapisany materiał'
        ev['snapshot']['volume'] = None
        with tempfile.TemporaryDirectory() as folder:
            store = KI.Store(Path(folder) / 'test.sqlite3')
            with store.transaction() as c:
                c.execute('INSERT INTO events VALUES(?,?,?,?,?)', ('e', 'AAA.WA', '1h', NOW.isoformat(), KI.json_text(ev)))
                c.execute('INSERT INTO analysis_jobs(event_id,state,context,updated_at) VALUES(?,?,?,?)',
                          ('e', 'BUSY_AI', KI.json_text(ctx), NOW.isoformat()))
            self.assertTrue(KI.filter_incomplete_analysis_material(store, 'e', ev))
            with store.connection() as c:
                saved = json.loads(c.execute('SELECT context FROM analysis_jobs').fetchone()[0])
                self.assertEqual(saved['audit_note'], ctx['audit_note'])

    def test_schema_and_prompt_reference_local_proofs_without_second_model(self):
        ev, ctx, result = self.sample()
        schema = KI.analysis_schema(ev['snapshot'], ctx)
        self.assertIn('decision', schema['required'])
        self.assertEqual(schema['properties']['decision']['properties']['verdict']['enum'], ['ALIGNED'])
        ctx['ai_preflight'] = KI.automatic_ai_preflight(ev, ctx)
        request = KI.event_analysis_request(ev, ctx)
        data = json.loads(request['messages'][-1]['content'])
        self.assertEqual(data['proved_event']['analysis_manifest']['local_review']['verdict'], 'ALIGNED')
        self.assertIn('required_reason_codes', request['messages'][0]['content'])
        self.assertEqual(request['model'], 'gpt-4o-mini')

    def test_good_typed_decision_survives_validation_and_revalidation(self):
        ev, ctx, result = self.sample()
        clean = KI.validate_event_analysis(result, ev['snapshot'], ctx)
        self.assertFalse(KI.analysis_publication_issues(clean, True))
        self.assertEqual(KI.validate_event_analysis(clean, ev['snapshot'], ctx), clean)
        self.assertIn('Powód:', KI.opportunity_message('e', ev, ctx, clean))

    def test_wrong_or_unproved_decision_blocks_publication_without_repair(self):
        for decision in ({'verdict': 'MIXED', 'reason_codes': ['TECH_SUPPORT']},
                         {'verdict': 'ALIGNED', 'reason_codes': ['INVENTED']},
                         {'verdict': 'ALIGNED', 'reason_codes': []},
                         {'verdict': 'ALIGNED', 'reason_codes': 12}):
            ev, ctx, result = self.sample()
            result['decision'] = decision
            clean = KI.validate_event_analysis(result, ev['snapshot'], ctx)
            self.assertTrue(KI.analysis_publication_issues(clean, True))
            self.assertEqual(KI.validate_event_analysis(clean, ev['snapshot'], ctx), clean)

    def test_mixed_requires_retained_interpretations_on_both_sides(self):
        ev, ctx, result = self.sample()
        ev['snapshot']['indicators']['last_macd_hist'] = -.1
        ctx['analysis_manifest'] = KI.build_analysis_manifest(ev, ctx)
        result['decision'] = {'verdict': 'MIXED', 'reason_codes': ['TECH_MIXED']}
        result['assessment']['movement'] = 'Potwierdzony wzrost ma mieszane wskazania.'
        clean = KI.validate_event_analysis(result, ev['snapshot'], ctx)
        self.assertTrue(KI.analysis_publication_issues(clean, True))
        result['technical'][1] = {'metric': 'last_macd_hist', 'interpretation': 'Ujemny histogram osłabia wskazania wzrostowe.'}
        clean = KI.validate_event_analysis(result, ev['snapshot'], ctx)
        self.assertFalse(KI.analysis_publication_issues(clean, True))

    def test_dominant_risk_cannot_be_hidden_behind_quote_limitation(self):
        ev, ctx, result = self.sample()
        ev['snapshot']['ohlc']['high'] = 110
        ctx['analysis_manifest'] = KI.build_analysis_manifest(ev, ctx)
        result['decision'] = {'verdict': 'RISK_DOMINANT', 'reason_codes': ['ADVERSE_RETRACE']}
        clean = KI.validate_event_analysis(result, ev['snapshot'], ctx)
        self.assertTrue(KI.analysis_publication_issues(clean, True))
        result['assessment']['risk'] = 'Cofnięcie osłabia wzrost; brak ofert ogranicza ocenę ryzyka wykonania.'
        clean = KI.validate_event_analysis(result, ev['snapshot'], ctx)
        self.assertFalse(KI.analysis_publication_issues(clean, True))

    def test_closed_activity_contradiction_is_blocked(self):
        ev, ctx, result = self.sample()
        s = ev['snapshot']
        s.update(candle_status='CLOSED', candle_end=NOW.isoformat(), rvol=.5, volume=50000.)
        ctx['analysis_manifest'] = KI.build_analysis_manifest(ev, ctx)
        result['assessment']['activity'] = 'Wolumen jest powyżej średniej.'
        clean = KI.validate_event_analysis(result, s, ctx)
        self.assertTrue(KI.analysis_publication_issues(clean, True))

    def test_copied_decision_does_not_excuse_contradictory_histogram_text(self):
        ev, ctx, result = self.sample()
        result['technical'][1] = {'metric': 'last_macd_hist', 'interpretation': 'Ujemny histogram osłabia wzrost.'}
        clean = KI.validate_event_analysis(result, ev['snapshot'], ctx)
        self.assertTrue(KI.analysis_publication_issues(clean, True))

    def test_rejected_decision_keeps_raw_response_and_has_no_delivery_or_retry(self):
        ev, ctx, result = self.sample()
        result['decision']['verdict'] = 'MIXED'
        body = {'model': 'test', 'choices': [{'finish_reason': 'stop', 'message': {'content': json.dumps(result)}}]}
        clean, metadata = KI.parse_event_analysis_response(body, ev['snapshot'], ctx)
        with tempfile.TemporaryDirectory() as folder:
            store = KI.Store(Path(folder) / 'test.sqlite3')
            with store.transaction() as c:
                c.execute('INSERT INTO events VALUES(?,?,?,?,?)', ('e', 'AAA.WA', '1h', NOW.isoformat(), KI.json_text(ev)))
                c.execute('INSERT INTO analysis_jobs(event_id,state,context,updated_at) VALUES(?,?,?,?)', ('e', 'BUSY_AI', KI.json_text(ctx), NOW.isoformat()))
            KI.finish_analysis(store, 'e', clean, metadata)
            with store.connection() as c:
                row = c.execute('SELECT state,result,next_attempt_at FROM analysis_jobs').fetchone()
                self.assertEqual(row['state'], 'REVIEW_REQUIRED')
                self.assertIsNone(row['next_attempt_at'])
                self.assertEqual(json.loads(row['result'])['provider']['raw_response'], body)
                self.assertEqual(c.execute('SELECT COUNT(*) FROM outbox').fetchone()[0], 0)


if __name__ == '__main__':
    unittest.main()
