"""Regresja ręcznego GPT. Jawne dane wejściowe; bez API i bez mocków."""
import copy
import json
from pathlib import Path
import unittest
import KI


class ManualValidationTests(unittest.TestCase):
    def setUp(self):
        self.context = {
            'ticker': '3RG.WA', 'purpose': 'ticker_analysis', 'report_version': 3,
            'snapshot': {
                'ticker': '3RG.WA', 'company_name': '3R Games S.A.',
                'price': .686, 'volume': 1171., 'rvol': .68, 'currency': 'PLN',
                'candle_status': 'CLOSED', 'acquired_at': '2026-10-08T09:15:02.258650+00:00',
                'indicators': {'rsi': 41.48, 'ma_fast': .6954, 'ma_slow': .6971, 'adx': 51.40},
                'spread': {'bid': .686, 'ask': .696, 'spread_pct': 1.45, 'freshness_confirmed': False},
            },
            'research': {'sources': []},
        }
        self.reply = {'answer': 'Opis danych.', 'metrics': [], 'facts': [], 'risks': [], 'missing': []}

    def render(self, text, context=None):
        return KI.render_manual_research_reply({**self.reply, 'answer': text}, context or self.context)

    def test_exact_issuer_name_with_digit_is_not_a_market_number(self):
        self.assertIn('3R Games S.A.', self.render('Spółka 3R Games S.A. ma cenę {{metric:price}}.'))

    def test_name_exception_does_not_admit_other_issuers_or_numbers(self):
        for text in ('Spółka 4R Games S.A.', 'Spółka 3R Games S.A. ma cenę 999 PLN.',
                     'Spółka X3R Games S.A.', 'Spółka 3R Games S.A.99'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                self.render(text)

    def test_missing_or_foreign_snapshot_cannot_authorize_name(self):
        for change in ({'company_name': None}, {'ticker': 'OTHER.WA'}):
            context = copy.deepcopy(self.context)
            context['snapshot'].update(change)
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.render('Spółka 3R Games S.A.', context)

    def test_name_is_literal_not_a_regex_pattern(self):
        context = copy.deepcopy(self.context)
        context['snapshot']['company_name'] = '3R (Games)+ S.A.'
        self.assertIn('3R (Games)+ S.A.', self.render('Emitent: 3R (Games)+ S.A.', context))
        with self.assertRaises(ValueError):
            self.render('Emitent: 3R Games S.A.', context)

    def test_rvol_threshold_is_distinct_from_measured_rvol(self):
        rendered = self.render('RVOL {{metric:rvol}}; próg KI {{threshold:rvol_min}}.')
        self.assertIn('0,68 ×', rendered)
        self.assertIn('1,50×', rendered)
        for suffix in ('×', ' ×'):
            self.assertNotIn('××', self.render('Próg {{threshold:rvol_min}}' + suffix))

    def test_threshold_units_and_unknown_keys_are_rejected(self):
        for text in ('Próg {{threshold:rvol_min}}%.', 'Próg {{threshold:rvol_min}} USD.',
                     'Próg {{threshold:unknown}}.', 'Próg {{threshold:spread_risk_pct}} ×.'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                self.render(text)

    def test_direct_numbers_stay_rejected(self):
        for text in ('RVOL poniżej progu 1,50.', 'Cena 0,686 PLN.', 'RSI 99.', 'Raport 2026.'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                self.render(text)

    def test_saved_response_replay_preserves_original_and_all_sentences(self):
        original = json.loads(Path(__file__).with_name('odpowiedz_3RG.json').read_text(encoding='utf-8'))
        before = copy.deepcopy(original)
        with self.assertRaises(ValueError):
            KI.render_manual_research_reply(original, self.context)
        bound = copy.deepcopy(original)
        # Jawna wersja testowa; oryginał i baza użytkownika nie są modyfikowane.
        self.assertEqual(bound['answer'].count('progu 1,50'), 1)
        bound['answer'] = bound['answer'].replace('progu 1,50', 'progu {{threshold:rvol_min}}')
        rendered = KI.render_manual_research_reply(bound, self.context)
        self.assertIn('3R Games S.A.', rendered)
        self.assertIn('progu 1,50×', rendered)
        self.assertIn('pełniejszy obraz potencjalnych zmian na rynku.', rendered)
        self.assertNotIn('Pominięto fragment', rendered)
        self.assertEqual(original, before)

    def test_request_explains_rvol_and_advertises_allowed_thresholds(self):
        request = KI.gpt_chat_request('Co pokazują dane?', self.context, [])
        instructions = request['messages'][0]['content']
        self.assertIn('{{threshold:rvol_min}}', instructions)
        self.assertIn('RVOL mierzy aktywność wolumenową', instructions)
        self.assertIn('nie momentum ceny', instructions)
        self.assertIn('Nie wpisuj progu jako samodzielnej liczby', instructions)
        self.assertIn('nazwę emitenta', instructions)

    def test_existing_spread_threshold_and_metric_protection_remain(self):
        self.assertIn('2%', self.render('Próg {{threshold:spread_risk_pct}}.'))
        for text in ('Cena {{metric:missing}}.', 'Cena {{metric:price}} USD.', 'Kup akcje.'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                self.render(text)


if __name__ == '__main__':
    unittest.main(verbosity=2)
