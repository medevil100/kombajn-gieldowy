"""Wspólny kontrakt alertów wszystkich tickerów; bez usług sieciowych."""
import tempfile
import unittest
from pathlib import Path
import KI
from test_repair_20261024 import NOW


class AlertQualityTests(unittest.TestCase):
    def sample(self,ticker='AAA.WA',change=-4.):
        snap=KI.opportunity_test_snapshot(NOW,ticker=ticker,price=1.2)
        snap['indicators']={'rsi':40.,'rvol':2.,'adx':30.,'atr':.1,'ma_fast':1.3,'ma_slow':1.4}
        snap['price_matrix']={'anchor_price':1.25,'change_pct':change,'state':'CONFIRMED','consecutive_reads':3}
        snap['rvol']=2.
        evidence={'kind':'CONFIRMED_OPPORTUNITY','snapshot':snap,'reasons':['PRICE_MATRIX_3_READS'],
                  'ranking':{'score':40,'risk':{'label':'Ryzyko podwyższone','reasons':['Szeroki spread.']}}}
        result={'technical':[{'metric':'rsi','interpretation':'RSI wskazuje słabe momentum ceny.'},
                             {'metric':'rvol','interpretation':'RVOL potwierdza podwyższoną aktywność częściowej świecy.'}],
                'context':[],'hypotheses':[],'risks':[],'missing':[]}
        return evidence,result

    def test_direction_is_shared_across_arbitrary_polish_and_us_tickers(self):
        for ticker in ('AAA.WA','XYZ','BRK.B','3RG.WA'):
            for change,label in ((-4.,'POTWIERDZONY SPADEK'),(4.,'POTWIERDZONY WZROST')):
                ev,result=self.sample(ticker,change)
                text=KI.opportunity_message('e',ev,{'sources':[]},result)
                self.assertTrue(text.startswith(label+' · '+ticker))
                self.assertNotIn('OKAZJA',text)
                self.assertIn('Ocena:',text)
                self.assertNotIn('MACD hist.',text)

    def test_diagnostics_are_short_but_saved_result_is_not_mutated(self):
        ev,result=self.sample()
        result=KI.ValidatedAnalysis({**result,'quality_issues':['technical[4]: szczegół diagnostyczny (usunięto).']})
        text=KI.opportunity_message('e',ev,{'sources':[]},result)
        self.assertIn('Analiza częściowa',text)
        self.assertNotIn('technical[4]',text)
        self.assertIn('technical[4]',result['quality_issues'][0])

    def test_one_statement_and_two_correlated_metrics_do_not_pass(self):
        ev,result=self.sample()
        result['technical']=result['technical'][:1]
        self.assertTrue(KI.analysis_publication_issues(result))
        result['technical'].append({'metric':'roc','interpretation':'Momentum jest ujemne.'})
        self.assertTrue(KI.analysis_publication_issues(result))
        self.assertIn('Wymaga sprawdzenia',KI.opportunity_message('e',ev,{'sources':[]},{**result,'technical':result['technical'][:1]}))

    def test_atr_without_reference_and_directionless_adx_are_removed(self):
        ev,result=self.sample()
        for metric,text in [('atr','Wartość ATR sugeruje umiarkowaną zmienność.'),
                            ('adx','Wysoka wartość ADX wskazuje na silny trend.')]:
            raw={**result,'technical':[{'metric':metric,'interpretation':text}]}
            clean=KI.validate_event_analysis(raw,ev['snapshot'],{'sources':[]})
            self.assertEqual(clean['technical'],[])
            self.assertTrue(KI.analysis_publication_issues(clean))

    def test_insufficient_automatic_analysis_is_saved_without_outbox(self):
        ev,result=self.sample();result['technical']=result['technical'][:1]
        with tempfile.TemporaryDirectory() as folder:
            store=KI.Store(Path(folder)/'test.sqlite3')
            with store.transaction() as c:
                c.execute('INSERT INTO events VALUES(?,?,?,?,?)',('e','AAA.WA','1h',NOW.isoformat(),KI.json_text(ev)))
                c.execute('INSERT INTO analysis_jobs(event_id,state,context,updated_at) VALUES(?,?,?,?)',('e','BUSY_AI',KI.json_text({'sources':[]}),NOW.isoformat()))
            KI.finish_analysis(store,'e',result,{'raw_response':{'retained':True}},now=NOW)
            with store.connection() as c:
                self.assertEqual(c.execute('SELECT state FROM analysis_jobs').fetchone()[0],'REVIEW_REQUIRED')
                self.assertEqual(c.execute('SELECT COUNT(*) FROM outbox').fetchone()[0],0)
                self.assertIn('publication_issues',c.execute('SELECT result FROM analysis_jobs').fetchone()[0])


if __name__=='__main__':unittest.main()
