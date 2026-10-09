"""Stage D: real pure reporting contracts, no API, Streamlit or SQLite calls."""
import unittest
import json
import KI


class ReportContractTests(unittest.TestCase):
    def sample(self, state='CONFIRMED'):
        snap={
            'ticker':'ADV.WA','interval':'1h','price':0.65,'currency':'PLN',
            'volume':3500,'average_volume':None,'rvol':None,
            'acquired_at':'2026-10-09T09:30:05+00:00','candle_time':'2026-10-09T11:00:00+02:00',
            'candle_end':'2026-10-09T12:00:00+02:00','candle_status':'OPEN',
            'ohlc':{'open':0.60,'high':0.65,'low':0.58,'close':0.65},
            'price_matrix':{'state':state,'anchor_price':0.576,'anchor_at':'2026-10-09T08:00:00+00:00',
                            'change_pct':12.847222,'consecutive_reads':3 if state=='CONFIRMED' else 2},
            'indicators':{},'spread':{'freshness_confirmed':False},
            'previous_closed':{'open':0.58,'close':0.6,'rvol':None,'time':'2026-10-09T10:00:00+02:00'},
        }
        return {'ticker':'ADV.WA','snapshot':snap,'group':'TOP' if state=='CONFIRMED' else 'EARLY',
                'score':60,'parts':{'Ruch':30,'Aktywność':0,'Technika':30,'Kontekst':0},
                'quality':'Okazja','estimated_turnover':2275,'rvol':None,
                'risk':KI.opportunity_risk(snap), 'confirms':['Trzy odczyty potwierdziły wzrost'],
                'weakens':[], 'missing':['RVOL bieżącej świecy']}

    def test_01_independent_three_sections_and_true_reference(self):
        row=self.sample()
        original=json.dumps(row,sort_keys=True)
        got=KI.opportunity_report_sections(row)
        self.assertEqual(list(got),['detection','quality','risk'])
        self.assertIn('Potwierdzony',got['detection']['summary'])
        self.assertIn('0,5760', '\n'.join(got['detection']['details']))
        self.assertIn('3 / 3', '\n'.join(got['detection']['details']))
        self.assertIn('60/100',got['quality']['summary'])
        self.assertIn('Aktywność: 0/30','\n'.join(got['quality']['details']))
        self.assertIn('Brak danych','\n'.join(got['quality']['details']))
        self.assertIn('niepotwierdzona','\n'.join(got['risk']['details']))
        self.assertEqual(original,json.dumps(row,sort_keys=True))

    def test_02_missing_spread_does_not_mean_safe_or_no_growth(self):
        got=KI.opportunity_report_sections(self.sample())
        self.assertIn('nieustalone',got['risk']['summary'].lower())
        self.assertNotIn('Brak ruchu',got['detection']['summary'])
        self.assertIn('2 275', '\n'.join(got['risk']['details']))
        self.assertIn('Szacowany', '\n'.join(got['risk']['details']))

    def test_03_candidate_is_not_reported_as_confirmed(self):
        got=KI.opportunity_report_sections(self.sample('CANDIDATE'))
        self.assertIn('Niepotwierdzony',got['detection']['summary'])
        self.assertIn('2 / 3','\n'.join(got['detection']['details']))

    def test_04_gpt_request_has_three_distinct_dimensions_but_no_copy_of_history(self):
        row=self.sample()
        row['snapshot']['chart_history']=[{'close':0.6} for _ in range(100)]
        evidence={'kind':'CONFIRMED_OPPORTUNITY','snapshot':row['snapshot'],'ranking':row}
        request=KI.event_analysis_request(evidence,{'sources':[],'cutoff':row['snapshot']['acquired_at']})
        system=request['messages'][0]['content']
        prompt=json.loads(request['messages'][1]['content'])
        for phrase in ('detekcj','jakość ruchu','ryzyko','przyczyny'):
            self.assertIn(phrase,system.lower())
        self.assertNotIn('chart_history',prompt['proved_event']['snapshot'])
        self.assertNotIn('snapshot',prompt['proved_event']['ranking'])
        self.assertEqual(request['response_format']['json_schema']['schema']['required'],
                         ['technical','context','hypotheses','risks','missing'])

    def test_05_autoreport_prints_three_layers_without_claiming_cause(self):
        row=self.sample();evidence={'kind':'CONFIRMED_OPPORTUNITY','snapshot':row['snapshot'],'ranking':row}
        response={'technical':[],'context':[],'hypotheses':[],'risks':[],'missing':[]}
        output=KI.analysis_message('id',evidence,{'sources':[]},response,limit=False)
        self.assertIn('1. DETEKCJA RUCHU',output)
        self.assertIn('2. JAKOŚĆ RUCHU',output)
        self.assertIn('3. RYZYKO',output)
        self.assertIn('Przyczyna ruchu nieustalona',output)
        self.assertLess(output.index('1. DETEKCJA'),output.index('2. JAKOŚĆ'))

    def test_06_compact_telegram_has_sections_but_never_calls_api(self):
        row=self.sample();evidence={'kind':'CONFIRMED_OPPORTUNITY','snapshot':row['snapshot'],'ranking':row}
        response={'technical':[],'context':[],'hypotheses':[],'risks':[],'missing':[]}
        msg=KI.opportunity_message('id',evidence,{'sources':[]},response)
        self.assertIn('1. DETEKCJA RUCHU',msg)
        self.assertIn('2. JAKOŚĆ RUCHU',msg)
        self.assertIn('3. RYZYKO',msg)
        self.assertIn('przyczyna nieustalona',msg.lower())


if __name__=='__main__':
    unittest.main(verbosity=2)
