"""Offline: pełny kontrakt liczb, izolacja danych i rzeczywiste SQLite; bez mocków/API."""
import copy
import json
import re
import tempfile
import unittest
from pathlib import Path
import KI
import sprawdz_raporty


def context(ticker='AAT.WA', currency='PLN'):
    # Jawne dane testowe. 212 pochodzi z tekstu GPT, nie jest potwierdzonym
    # odczytem użytkownika. Dopiero test na jego bazie może to potwierdzić.
    return {'ticker': ticker, 'report_version': 3, 'purpose': 'ticker_analysis',
        'snapshot': {'ticker': ticker, 'company_name': 'Alta S.A.', 'interval': '1h',
            'currency': currency, 'acquired_at': '2026-10-08T11:33:31+00:00',
            'candle_time': '2026-10-08T10:00:00+00:00', 'candle_end': '2026-10-08T11:00:00+00:00',
            'candle_status': 'CLOSED', 'price': 1.66, 'volume': 6589, 'average_volume': 4907,
            'rvol': 1.34, 'ohlc': {'open': 1.66, 'high': 1.66, 'low': 1.66, 'close': 1.66},
            'previous_closed': {'close': 1.65, 'open': 1.65, 'volume': 3000, 'rvol': .61},
            'indicators': {'ma_fast': 1.677, 'ma_slow': 1.6647, 'rsi': 43.64, 'adx': 18.63, 'roc': -1.78, 'obv': -16803},
            'spread': {'bid': 1.65, 'ask': 1.70, 'spread_pct': 2.99, 'freshness_confirmed': False},
            'carried_price_candles': [{'time': str(i)} for i in range(128)]},
        'previous_snapshot': {'ticker': ticker, 'interval': '1h', 'currency': currency,
            'acquired_at': '2026-10-08T11:18:31+00:00', 'candle_time': '2026-10-08T10:00:00+00:00',
            'candle_status': 'OPEN', 'price': 1.66, 'volume': 212, 'rvol': .04,
            'ohlc': {'open': 1.66}, 'indicators': {'rsi': 40.25}},
        'research': {'sources': [], 'status': 'DONE'}}


def reply(text):
    return {'answer': text, 'metrics': [], 'facts': [], 'risks': [], 'missing': []}


class NumericContractTests(unittest.TestCase):
    def render(self, text, ctx=None):
        return KI.render_manual_research_reply(reply(text), ctx or context())

    def test_current_previous_candle_previous_read_and_history_are_distinct(self):
        text = self.render('Otwarcie {{metric:candle_open}}; poprzednie zamknięcie {{metric:previous_close}}; '
            'poprzedni odczyt {{metric:previous_snapshot_price}}. '
            'Wolumen poprzedniej świecy {{metric:previous_candle_volume}}; '
            'poprzedniego odczytu {{metric:previous_snapshot_volume}}; średni {{metric:average_volume}}. '
            'Przeniesione ceny: {{metric:carried_price_candles_count}}.')
        for fragment in ('1,6600 PLN', '1,6500 PLN', '3 000', '212', '4 907', '128'):
            self.assertIn(fragment, text)
        self.assertNotIn('{{', text)

    def test_derived_changes_use_the_named_reference(self):
        c = context(); c['previous_snapshot']['price'] = 1.50
        rendered = self.render('Świeca {{metric:candle_change_pct}}, '
            'zamknięcie {{metric:previous_close_change_pct}}, odczyt {{metric:scan_change_pct}}.', c)
        self.assertIn('0,00 %', rendered)
        self.assertIn('0,61 %', rendered)
        self.assertIn('10,67 %', rendered)

    def test_previous_identity_interval_currency_and_time_are_verified(self):
        for change in ({'ticker':'FOREIGN'}, {'interval':'1d'}, {'currency':'USD'},
                       {'acquired_at':'2026-10-08T11:34:00Z'}, {'acquired_at':None}, {'ticker':None}):
            c = context(); c['previous_snapshot'].update(change)
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.render('Wolumen {{metric:previous_snapshot_volume}}.', c)
            request = KI.gpt_chat_request('Dane?', c, [])
            sent = json.loads(request['messages'][-1]['content'])['context']
            self.assertIsNone(sent.get('previous_snapshot'))

    def test_foreign_current_snapshot_is_rejected_before_rendering(self):
        c = context(); c['snapshot']['ticker'] = 'FOREIGN'
        with self.assertRaises(ValueError):
            self.render('Cena {{metric:price}}.', c)

    def test_missing_is_not_zero_but_explicit_zero_is_valid(self):
        c = context(); c['snapshot'].pop('carried_price_candles'); c['previous_snapshot'] = None
        for key in ('carried_price_candles_count','previous_snapshot_volume'):
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.render('{{metric:'+key+'}}', c)
        c['snapshot']['carried_price_candles'] = []
        c['snapshot']['volume'] = 0
        self.assertIn('Historia 0; wolumen 0.', self.render('Historia {{metric:carried_price_candles_count}}; wolumen {{metric:volume}}.', c))

    def test_units_precision_and_invalid_references(self):
        text = self.render('ROC {{metric:roc}}%; RSI {{metric:rsi}}; OBV {{metric:obv}}.')
        self.assertIn('-1,78 %', text); self.assertIn('43,64', text); self.assertIn('-16 803', text)
        for token in ('{{metric:previous_snapshot_volume}} PLN', '{{metric:carried_price_candles_count}}%',
                      '{{metric:scan_change_pct}} USD', '{{metric:invented}}'):
            with self.subTest(token=token), self.assertRaises(ValueError): self.render(token)

    def test_error_identifies_all_unbound_numbers_and_section(self):
        with self.assertRaises(ValueError) as caught:
            self.render('RVOL poniżej progu 1,50. Wcześniejszy wolumen 212. Historia zawiera 128 przedziałów.')
        for fragment in ('answer','1,50','212','128','Historia'):
            self.assertIn(fragment, str(caught.exception))
        bad = reply('Opis.'); bad['risks'] = ['Cena 999 PLN.']
        with self.assertRaises(ValueError) as caught: KI.render_manual_research_reply(bad, context())
        self.assertIn('risks[0]', str(caught.exception))
        self.assertIn('999', str(caught.exception))

    def test_each_risk_is_checked_even_when_only_five_are_displayed(self):
        bad = reply('Opis.'); bad['risks'] = ['Opis.'] * 5 + ['Cena 999 PLN.']
        with self.assertRaises(ValueError): KI.render_manual_research_reply(bad, context())

    def test_prompt_provides_source_bound_catalog_and_symbolic_input(self):
        c = context(); before = copy.deepcopy(c)
        request = KI.gpt_chat_request('Dane?', c, [])
        sent = json.loads(request['messages'][-1]['content'])['context']
        for key in ('previous_snapshot_volume','carried_price_candles_count','average_volume','previous_close'):
            self.assertEqual(sent['numeric_references'][key], '{{metric:'+key+'}}')
        self.assertEqual(sent['snapshot']['volume'], '{{metric:volume}}')
        self.assertEqual(sent['previous_snapshot']['volume'], '{{metric:previous_snapshot_volume}}')
        catalog = sent['numeric_catalog']
        self.assertEqual(catalog['previous_snapshot_volume']['value'], 212)
        self.assertEqual(catalog['previous_snapshot_volume']['source'], 'previous_snapshot.volume')
        self.assertEqual(catalog['carried_price_candles_count']['value'], 128)
        local_text = json.dumps(sent['local_analysis'], ensure_ascii=False)
        self.assertIn('{{metric:carried_price_candles_count}}', local_text)
        self.assertNotIn('Historia zawiera 128', local_text)
        self.assertNotIn('RVOL poniżej 1,50', local_text)
        self.assertEqual(c, before)
        instructions = request['messages'][0]['content']
        self.assertIn('nie oznacza aktywności poniżej średniej', instructions)
        self.assertIn('Brak wyników Tavily nie dowodzi braku informacji', instructions)

    def test_gpt_local_conclusion_uses_fixed_matrix_instead_of_two_candle_filter(self):
        c = context()
        c['snapshot']['price_matrix'] = {'state':'CANDIDATE','anchor_price':1.50,
            'change_pct':10.67,'consecutive_reads':2}
        report = KI.company_snapshot_report(c['snapshot'], c['previous_snapshot'])
        self.assertIn('matryca oczekuje na potwierdzenie', report['conclusion'])
        self.assertFalse(report['confirmed'])
        self.assertNotIn('otwarcia świecy', report['conclusion'])
        self.assertNotIn('dwie świece', report['conclusion'])

        request = KI.gpt_chat_request('Co pokazują dane?', c, [])
        sent = json.loads(request['messages'][-1]['content'])['context']['local_analysis']
        self.assertEqual(sent['conclusion'], report['conclusion'])
        self.assertFalse(sent['confirmed'])
        self.assertNotIn('filtra dwóch świec', json.dumps(sent, ensure_ascii=False))

        c['snapshot']['price_matrix']['state'] = 'CONFIRMED'
        confirmed = KI.company_snapshot_report(c['snapshot'], c['previous_snapshot'])
        self.assertIn('Matryca potwierdza ruch', confirmed['conclusion'])
        self.assertTrue(confirmed['confirmed'])

    def test_missing_matrix_is_not_replaced_by_legacy_two_candle_claim(self):
        report = KI.company_snapshot_report(context()['snapshot'], None)
        self.assertIn('Brak danych matrycy', report['conclusion'])
        self.assertIsNone(report['confirmed'])
        self.assertNotIn('filtra dwóch świec', report['conclusion'])

    def test_catalog_is_generic_across_tickers_and_currencies(self):
        for ticker, currency, number in (('AAT.WA','PLN',212),('XYZ','USD',453),('7LV.WA','PLN',0)):
            c = context(ticker, currency); c['previous_snapshot']['volume'] = number
            c['snapshot']['company_name'] = ticker + ' Holdings'
            text = self.render('Emitent '+c['snapshot']['company_name']+': '
                '{{metric:previous_snapshot_volume}}, {{metric:price}}.', c)
            self.assertIn(str(number), text); self.assertIn(currency, text)

    def test_aat_original_is_preserved_and_explicit_binding_replays(self):
        original = json.loads(Path(__file__).with_name('odpowiedz_AAT.json').read_text(encoding='utf-8'))
        before = copy.deepcopy(original)
        with self.assertRaises(ValueError) as caught: KI.render_manual_research_reply(original, context())
        for number in ('1,50','212','128'): self.assertIn(number, str(caught.exception))
        bound = copy.deepcopy(original)
        for raw, token in [('progu 1,50','progu {{threshold:rvol_min}}'),
                           ('wynosił on 212','wynosił on {{metric:previous_snapshot_volume}}'),
                           ('Historia zawiera 128','Historia zawiera {{metric:carried_price_candles_count}}')]:
            self.assertEqual(bound['answer'].count(raw),1)
            bound['answer'] = bound['answer'].replace(raw, token)
        body = {'choices':[{'finish_reason':'stop','message':{'content':json.dumps(bound)}}]}
        rendered, metadata = KI.parse_gpt_chat_response(body, context())
        self.assertIn('wynosił on 212', rendered)
        self.assertIn('Historia zawiera 128', rendered)
        self.assertNotIn('Pominięto fragment', rendered)
        self.assertEqual(original, before)
        # Format acceptance does not certify the old model's RVOL interpretation.
        c = context(); c['previous_snapshot'] = None
        with self.assertRaises(KI.ServiceError): KI.parse_gpt_chat_response(body,c)

    def test_database_context_and_response_roundtrip_without_network(self):
        c = context()
        with tempfile.TemporaryDirectory() as folder:
            store = KI.Store(Path(folder)/'isolated.sqlite3')
            for snap in (c['previous_snapshot'],c['snapshot']): KI.detect_market(store,snap)
            real = {**KI.gpt_chat_context(store,c['ticker']), 'report_version':3, 'purpose':'ticker_analysis', 'research':{'sources':[]}}
            turn = KI.begin_gpt_chat(store,'Dane?',real)
            body = {'choices':[{'finish_reason':'stop','message':{'content':json.dumps(reply(
                'Wolumen {{metric:volume}}; poprzedni odczyt {{metric:previous_snapshot_volume}}.'))}}]}
            text, metadata = KI.parse_gpt_chat_response(body,real)
            KI.finish_gpt_chat(store,turn,text,metadata)
            with store.connection() as con:
                saved = con.execute('SELECT state,answer FROM gpt_chat_turns WHERE id=?',(turn,)).fetchone()
                self.assertEqual(saved['state'],'DONE'); self.assertIn('poprzedni odczyt 212',saved['answer'])
                self.assertEqual(con.execute('SELECT COUNT(*) FROM outbox').fetchone()[0],0)

    def test_api_schema_constrains_numbers_before_generation(self):
        schema = KI.gpt_chat_request('Dane?',context(),[])['response_format']['json_schema']['schema']
        pattern = schema['$defs']['bound_text']['pattern']
        for field in ('answer','risks','missing'):
            node = schema['properties'][field]
            if field != 'answer': node = node['items']
            self.assertEqual(node, {'$ref':'#/$defs/bound_text'})
        for text in ('Próg 1,50.', 'Wolumen 212.', 'Historia 128.', 'Cena 999 USD.',
                     '{{metric:missing}}', '{{threshold:invented}}', 'Raport 2026-10-08.', 'Cena ١٢٣.'):
            with self.subTest(text=text): self.assertIsNone(re.search(pattern,text))
        for text in ('Próg {{threshold:rvol_min}}.', 'Wolumen {{metric:previous_snapshot_volume}}.',
                     'Historia {{metric:carried_price_candles_count}}.', 'SMA {{parameter:ma_fast_window}}.',
                     'Emitent {{identity:company_name}}.', 'Brak danych.\nNie ustalono przyczyny.'):
            with self.subTest(text=text): self.assertIsNotNone(re.search(pattern,text))
        self.assertNotIn('pattern', schema['properties']['facts']['items']['properties']['fact'])

    def test_digit_names_and_interval_use_identity_references(self):
        c = context('3RG.WA'); c['snapshot']['company_name'] = '3R Games S.A.'
        rendered = self.render('Emitent {{identity:company_name}} ({{identity:ticker}}), {{identity:interval}}.',c)
        self.assertIn('3R Games S.A. (3RG.WA), 1h.',rendered)
        schema = KI.manual_research_schema(c)
        self.assertIsNone(re.search(schema['$defs']['bound_text']['pattern'],'Inna spółka 4R.'))
        with self.assertRaises(ValueError): self.render('{{identity:invented}}',c)

    def test_new_constants_render_once_and_reject_wrong_units(self):
        text = self.render('Próg RSI {{threshold:rsi_high}}, MACD {{parameter:macd_fast}} / '
            '{{parameter:macd_slow}}, średnia wolumenu {{parameter:volume_window}} świec.')
        self.assertIn('Próg RSI 70, MACD 12 / 26, średnia wolumenu 20 świec.',text)
        with self.assertRaises(ValueError): self.render('{{parameter:volume_window}}%')

    def test_report_diagnostics_read_saved_context_without_writing(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'isolated.sqlite3'
            store = KI.Store(path); c = context()
            turn = KI.begin_gpt_chat(store,'Dane?',c)
            raw = json.loads(Path(__file__).with_name('odpowiedz_AAT.json').read_text(encoding='utf-8'))
            KI.save_gpt_chat_metadata(store,turn,{'raw_response':[{'finish_reason':'stop','message':{'content':json.dumps(raw)}}]})
            KI.fail_gpt_chat(store,turn,'Zapisany blad do odczytu')
            with store.connection() as con: before = con.execute('SELECT * FROM gpt_chat_turns').fetchall()
            result = sprawdz_raporty.inspect_reports(path)[0]
            self.assertEqual(result['values']['previous_snapshot_volume'],212)
            self.assertEqual(result['values']['carried_price_candles_count'],128)
            for number in ('1,50','212','128'): self.assertIn(number,result['validation'])
            with store.connection() as con: after = con.execute('SELECT * FROM gpt_chat_turns').fetchall()
            self.assertEqual([tuple(r) for r in before],[tuple(r) for r in after])
        with tempfile.TemporaryDirectory() as folder:
            missing = Path(folder)/'missing.sqlite3'
            with self.assertRaises(Exception): sprawdz_raporty.inspect_reports(missing)
            self.assertFalse(missing.exists())


if __name__ == '__main__': unittest.main(verbosity=2)
