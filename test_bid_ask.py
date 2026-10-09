import unittest
import KI

class BidAskTests(unittest.TestCase):
    def test_report_prices_time_and_unconfirmed_freshness(self):
        snap={'currency':'USD','spread':KI.spread_from_info({'bid':1.,'ask':1.02})}
        rows=KI.quote_report_rows(snap)
        self.assertEqual(rows[0]['Wartość'],'1,0000 USD')
        self.assertEqual(rows[1]['Wartość'],'1,0200 USD')
        self.assertEqual(rows[2]['Wartość'],'1,98%')
        self.assertEqual(rows[3]['Wartość'],snap['spread']['acquired_at'])
        self.assertIn('Niepotwierdzona',rows[4]['Wartość'])
    def test_invalid_and_missing_quotes_not_zero_spread(self):
        for raw in ({},{'bid':0,'ask':1.},{'bid':2.,'ask':1.}):
            rows=KI.quote_report_rows({'spread':KI.spread_from_info(raw)})
            self.assertEqual(rows[2]['Wartość'],'Brak danych')
        self.assertEqual(KI.quote_report_rows({})[0]['Wartość'],'Brak danych')
    def test_manual_quote_does_not_mutate_saved_observation(self):
        snapshot={'ticker':'PLRX','price':1.,'currency':'USD','acquired_at':'2026-10-07T18:06:19Z'}
        context={'ticker':'PLRX','snapshot':snapshot}
        quote=KI.spread_from_info({'bid':1.,'ask':1.02})
        KI.attach_manual_quote(context,quote)
        self.assertNotIn('spread',snapshot)
        self.assertEqual(context['snapshot']['acquired_at'],snapshot['acquired_at'])
        self.assertEqual(context['snapshot']['spread'],quote)
    def test_quote_values_bound_in_gpt_comment(self):
        context={'ticker':'PLRX','report_version':3,'snapshot':{'currency':'USD','spread':KI.spread_from_info({'bid':1.,'ask':1.02})},'research':{'sources':[]}}
        reply={'answer':'Bid {{metric:bid}}, ask {{metric:ask}}, spread {{metric:spread_pct}}.','metrics':['bid','ask','spread_pct'],'facts':[],'risks':[],'missing':[]}
        text=KI.render_manual_research_reply(reply,context)
        self.assertIn('Bid 1,0000 USD',text)
        self.assertIn('spread 1,98 %',text)

if __name__=='__main__':unittest.main()
