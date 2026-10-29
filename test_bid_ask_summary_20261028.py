import unittest
import KI
import test_alert_quality_20261026 as fixture


class BidAskSummaryTests(unittest.TestCase):
    def test_values_and_calculated_spread_do_not_claim_quote_time(self):
        s={'currency':'PLN','spread':{'bid':1.,'ask':1.02,'spread_pct':999.,'acquired_at':'2026-10-28T12:00:00Z','freshness_confirmed':True}}
        text=KI.bid_ask_summary(s)
        self.assertIn('bid 1,0000 PLN',text);self.assertIn('ask 1,0200 PLN',text)
        self.assertIn('spread 1,98%',text);self.assertIn('świeżość niepotwierdzona',text)
        self.assertIn('pobrano 2026-10-28 13:00:00 CET',text)

    def test_partial_missing_and_crossed_quotes_are_not_invented(self):
        for quote in ({},{'bid':0,'ask':None},{'bid':2.,'ask':1.}):
            text=KI.bid_ask_summary({'spread':quote})
            self.assertIn('spread —',text);self.assertIn('świeżość niepotwierdzona',text)
        self.assertIn('niespójne',KI.bid_ask_summary({'spread':{'bid':2.,'ask':1.}}))

    def test_timestamped_quote_can_be_marked_fresh(self):
        s={'spread':{'bid':1.,'ask':1.01,'freshness_confirmed':True,'quote_time':'2026-10-28T12:00:00Z','acquired_at':'2026-10-28T12:00:20Z'}}
        self.assertIn('świeżość potwierdzona',KI.bid_ask_summary(s,now='2026-10-28T12:00:30Z'))
        self.assertIn('świeżość niepotwierdzona',KI.bid_ask_summary(s,now='2026-10-28T12:02:00Z'))

    def test_all_tickers_receive_same_compact_telegram_quote(self):
        for ticker in ('AAA.WA','XYZ','GNPX'):
            ev,result=fixture.AlertQualityTests().sample(ticker)
            ev['snapshot']['spread']={'bid':1.19,'ask':1.21,'acquired_at':ev['snapshot']['acquired_at']}
            text=KI.opportunity_message('e',ev,{'sources':[]},result)
            self.assertIn('Oferty: bid 1,1900',text);self.assertIn('ask 1,2100',text)
            self.assertLess(len(text),1500)


if __name__=='__main__':unittest.main()
