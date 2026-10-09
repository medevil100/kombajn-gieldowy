import unittest
import KI

class NumericRulesTests(unittest.TestCase):
    def render(self,text,spread=30.65):
        c={'ticker':'PLRX','report_version':3,'snapshot':{'spread':{'spread_pct':spread}},'research':{'sources':[]}}
        return KI.render_manual_research_reply({'answer':text,'metrics':[],'facts':[],'risks':[],'missing':[]},c)
    def test_real_rejected_risk(self):
        self.assertIn('2%',self.render('Ryzyko podwyższone z powodu spreadu bid/ask ≥ 2%.'))
    def test_threshold_does_not_accept_false_comparison(self):
        for value in (None,1.0):
            with self.assertRaises(ValueError):self.render('Spread bid/ask ≥ 2%.',value)
        with self.assertRaises(ValueError):self.render('Cena wynosi 2%.')
        with self.assertRaises(ValueError):self.render('Spread bid/ask ≥ 9%.')
    def test_metric_unit_once(self):
        text=self.render('Spread wynosi {{metric:spread_pct}}%.')
        self.assertIn('30,65 %.',text)
        self.assertNotIn('%%',text)
        mixed=self.render('Spread bid/ask ≥ 2%. Odczyt {{metric:spread_pct}}%, próg {{threshold:spread_risk_pct}}.')
        self.assertIn('Odczyt 30,65 %, próg 2%.',mixed)
        with self.assertRaises(ValueError):self.render('Spread wynosi {{metric:spread_pct}} USD.')
    def test_typed_threshold(self):
        self.assertIn('2%',self.render('Próg KI wynosi {{threshold:spread_risk_pct}}.'))
        with self.assertRaises(ValueError):self.render('Próg {{threshold:unknown}}.')

if __name__=='__main__':unittest.main()
