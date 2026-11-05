"""Natural alert regressions: VVOS/CRIS quote and uncalculated RR assertions."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

import KI
from analysis_verdict import narrative_errors, quote_status
import test_analysis_verdict_20261031 as fixtures


class AnalysisConsistencyTests(unittest.TestCase):
    def sample(self): return fixtures.AutonomousReviewTests().sample()

    def test_vvos_unmeasured_rr_and_available_offers_cannot_pass_as_valid(self):
        ev, ctx, result = self.sample()
        ev['snapshot']['spread'] = {'bid': 104., 'ask': 106., 'freshness_confirmed': False}
        ctx['analysis_manifest'] = KI.build_analysis_manifest(ev, ctx)
        result['assessment']['risk'] = 'Ryzyko jest podwyższone z powodu braku potwierdzonych danych bid/ask oraz słabej relacji potencjału do ryzyka.'
        clean = KI.validate_event_analysis(result, ev['snapshot'], ctx)
        self.assertTrue(KI.analysis_publication_issues(clean, True))
        issues = ' '.join(clean['quality_issues'])
        self.assertIn('relacji potencjału', issues)
        self.assertIn('Oferty są dostępne', issues)
        self.assertEqual(KI.validate_event_analysis(clean, ev['snapshot'], ctx), clean)

    def test_correct_unverified_quote_limitation_is_retained(self):
        ev, ctx, result = self.sample()
        ev['snapshot']['spread'] = {'bid': 104., 'ask': 106., 'freshness_confirmed': False}
        ctx['analysis_manifest'] = KI.build_analysis_manifest(ev, ctx)
        result['assessment']['risk'] = 'Świeżość ofert niepotwierdzona; relacja potencjału do ryzyka nie została wyznaczona.'
        clean = KI.validate_event_analysis(result, ev['snapshot'], ctx)
        self.assertFalse(KI.analysis_publication_issues(clean, True))

    def test_unknown_plan_cannot_gain_rr_claim_in_other_sections(self):
        ev, ctx, result = self.sample()
        for key in ('hypotheses', 'risks', 'missing'):
            changed = copy.deepcopy(result)
            changed[key] = ['Korzystna relacja zysku do ryzyka.']
            clean = KI.validate_event_analysis(changed, ev['snapshot'], ctx)
            self.assertTrue(KI.analysis_publication_issues(clean, True), key)

    def test_measured_low_rr_allows_unfavourable_but_not_favourable_claim(self):
        ev, ctx, result = self.sample()
        ctx['analysis_manifest']['trade_plan'] = {'status': 'INDICATIVE', 'rr1': .8}
        result['assessment']['risk'] = 'Niekorzystna relacja potencjału do ryzyka; brak ofert ogranicza wykonanie.'
        self.assertFalse(narrative_errors(result, ev['snapshot'], ctx['analysis_manifest']))
        result['assessment']['risk'] = 'Korzystna relacja potencjału do ryzyka.'
        self.assertTrue(narrative_errors(result, ev['snapshot'], ctx['analysis_manifest']))
        ctx['analysis_manifest']['trade_plan']['rr1'] = 1.5
        result['assessment']['risk'] = 'Słaba relacja potencjału do ryzyka.'
        self.assertTrue(narrative_errors(result, ev['snapshot'], ctx['analysis_manifest']))

    def test_negative_statement_does_not_assert_unmeasured_rr(self):
        ev, ctx, result = self.sample()
        for text in ('Nie można ocenić relacji potencjału do ryzyka.',
                     'Nie potwierdzono słabej relacji potencjału do ryzyka.',
                     'Brak dowodów na korzystną relację zysku do ryzyka.'):
            result['assessment']['risk'] = text
            self.assertFalse(narrative_errors(result, ev['snapshot'], ctx['analysis_manifest']), text)

    def test_inverted_and_incomplete_quotes_are_distinct_from_absent_values(self):
        ev, ctx, result = self.sample()
        for q, status in (({}, 'MISSING'), ({'bid': 104}, 'INCOMPLETE'),
                          ({'bid': 107, 'ask': 103}, 'INVERTED'), ({'bid': 104, 'ask': 106}, 'VALID')):
            ev['snapshot']['spread'] = q
            self.assertEqual(quote_status(ev['snapshot']), status)

    def test_cris_inverted_quotes_are_named_in_risk_and_prose_is_checked(self):
        ev, ctx, result = self.sample()
        ev['snapshot']['spread'] = {'bid': 107., 'ask': 103.}
        ctx['analysis_manifest'] = KI.build_analysis_manifest(ev, ctx)
        result['assessment']['risk'] = 'Brak bid/ask ogranicza ocenę ryzyka wykonania.'
        clean = KI.validate_event_analysis(result, ev['snapshot'], ctx)
        self.assertTrue(KI.analysis_publication_issues(clean, True))
        result['assessment']['risk'] = 'Niespójne bid/ask uniemożliwiają ocenę spreadu i ryzyka wykonania.'
        clean = KI.validate_event_analysis(result, ev['snapshot'], ctx)
        self.assertFalse(KI.analysis_publication_issues(clean, True))
        text = KI.opportunity_message('e', ev, ctx, clean)
        self.assertIn('niespójne bid/ask (bid powyżej ask)', text)
        self.assertNotIn('— brak bid/ask', text)

    def test_rejected_prose_keeps_raw_response_and_never_queues_delivery(self):
        ev, ctx, result = self.sample()
        result['assessment']['risk'] = 'Słaba relacja potencjału do ryzyka; brak ofert ogranicza wykonanie.'
        body = {'choices': [{'finish_reason': 'stop', 'message': {'content': json.dumps(result)}}]}
        clean, metadata = KI.parse_event_analysis_response(body, ev['snapshot'], ctx)
        with tempfile.TemporaryDirectory() as folder:
            store = KI.Store(Path(folder) / 'test.sqlite3')
            with store.transaction() as c:
                c.execute('INSERT INTO events VALUES(?,?,?,?,?)', ('e', 'AAA.WA', '1h', KI.utc_now(), KI.json_text(ev)))
                c.execute('INSERT INTO analysis_jobs(event_id,state,context,updated_at) VALUES(?,?,?,?)',
                          ('e', 'BUSY_AI', KI.json_text(ctx), KI.utc_now()))
            KI.finish_analysis(store, 'e', clean, metadata)
            with store.connection() as c:
                job = c.execute('SELECT state,result,next_attempt_at FROM analysis_jobs').fetchone()
                self.assertEqual(job['state'], 'REVIEW_REQUIRED')
                self.assertIsNone(job['next_attempt_at'])
                self.assertEqual(json.loads(job['result'])['provider']['raw_response'], body)
                self.assertEqual(c.execute('SELECT COUNT(*) FROM outbox').fetchone()[0], 0)


if __name__ == '__main__': unittest.main()
