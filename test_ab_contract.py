"""Etap A/B: offline tests for prompt data minimization and grounded numeric validator.
No calls to Yahoo, OpenAI, Tavily or Telegram.  No production SQLite files.
"""
import copy
import json
import unittest
import KI


class EtapAB(unittest.TestCase):
    def setUp(self):
        self.snapshot = {
            'ticker': 'AAA.WA', 'interval':'1h', 'currency': 'PLN',
            'price': 0.65, 'volume': 3500,
            'indicators': {'rsi': 55.0, 'last_macd_hist': 0.0031},
            'price_matrix': {'anchor_price': 0.576, 'change_pct':12.85, 'consecutive_reads':3},
            'chart_history': [{'time': str(n),'close': n/100} for n in range(150)],
            'carried_price_candles': [{'time':str(n)} for n in range(100)],
            'empty_trailing_source_candles': [{'time':str(n)} for n in range(70)],
        }
        self.context = {'sources':[{'id':'S1','content':'Spółka opublikowała raport okresowy.','url':'https://example.org/raport','published_at':'2026-10-08T10:00:00+00:00'}], 'received_at':'2026-10-08T10:15:00+00:00'}
        self.evidence = {'kind': 'CONFIRMED_OPPORTUNITY', 'sequence_id':'seq_1','snapshot': self.snapshot,
            'ranking':{'snapshot':self.snapshot, 'score':60,'parts':{'Ruch':30,'Aktywność':0,'Technika':30,'Kontekst':0},
            'risk':{'label':'Ryzyko nieustalone','missing':['spread']},'confirms':['Trzy kolejne odczyty']},
            'reasons':['PRICE_MATRIX_3_READS'], 'price_change_pct':12.85}
        self.result = {'technical':[{'metric':'rsi','interpretation':'RSI 55 potwierdza przewagę popytu.'}],
            'context':[{'source_id':'S1','fact':'Spółka opublikowała raport okresowy.'}],
            'hypotheses':['Przyczyna ruchu pozostaje nieustalona.'],
            'risks':['Brak potwierdzonego spreadu.'], 'missing':['Dane o bid i ask.']}

    def test_A_prompt_no_duplicate_snapshot_and_no_bulk_history(self):
        original = copy.deepcopy(self.evidence)
        request = KI.event_analysis_request(self.evidence,self.context)
        data = json.loads(request['messages'][1]['content'])['proved_event']
        self.assertIn('snapshot',data)
        self.assertIn('ranking',data)
        self.assertNotIn('snapshot',data['ranking'])
        self.assertNotIn('chart_history',data['snapshot'])
        self.assertNotIn('carried_price_candles',data['snapshot'])
        self.assertNotIn('empty_trailing_source_candles',data['snapshot'])
        self.assertEqual(data['snapshot']['price_matrix']['anchor_price'],.576)
        self.assertEqual(data['ranking']['risk']['label'],'Ryzyko nieustalone')
        self.assertEqual(data['ranking']['parts']['Technika'],30)
        self.assertEqual(self.evidence,original, 'No mutation in saved SQLite evidence')
        self.assertLess(len(request['messages'][1]['content']),4000)

    def test_B_technical_metric_number_is_verified_against_snapshot(self):
        allowed = copy.deepcopy(self.result)
        clean = KI.validate_event_analysis(allowed,self.snapshot,self.context)
        self.assertIn('RSI 55',clean['technical'][0]['interpretation'])

    def test_B_number_not_matching_metric_is_rejected(self):
        bad=copy.deepcopy(self.result)
        bad['technical'][0]['interpretation']='RSI 95 potwierdza przewagę popytu.'
        with self.assertRaisesRegex(ValueError,'technical\\[0\\].interpretation'):
            KI.validate_event_analysis(bad,self.snapshot,self.context)

    def test_B_unverified_numbers_and_commands_remain_forbidden(self):
        for k,text in [('risks','Spread 25 procent.'),('missing','Brak 123 zapisów.'),('hypotheses','BUY teraz.')]:
            with self.subTest(k=k):
                bad=copy.deepcopy(self.result)
                bad[k]=[text]
                with self.assertRaises(ValueError):KI.validate_event_analysis(bad,self.snapshot,self.context)

    def test_B_source_literal_still_required(self):
        bad=copy.deepcopy(self.result)
        bad['context'][0]['fact']='Spółka uzyskała milion zysku.'
        with self.assertRaises(ValueError):KI.validate_event_analysis(bad,self.snapshot,self.context)

    def test_B_response_parser_preserves_provider_usage(self):
        body={'model':'gpt-4o-mini','usage':{'prompt_tokens':500,'completion_tokens':100,'total_tokens':600},
            'choices':[{'finish_reason':'stop','message':{'content':json.dumps(self.result,ensure_ascii=False)}}]}
        result,meta=KI.parse_event_analysis_response(body,self.snapshot,self.context)
        self.assertEqual(meta['usage']['total_tokens'],600)
        self.assertEqual(result['technical'][0]['metric'],'rsi')

if __name__=='__main__':unittest.main(verbosity=2)
