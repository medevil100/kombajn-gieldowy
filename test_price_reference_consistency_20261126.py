"""Daily return and technical tracking base must never be interchangeable."""
import unittest

import KI
import company_narrative
import market_intelligence


class PriceReferenceConsistencyTests(unittest.TestCase):
    def snapshot(self,matrix):
        return {'ticker':'TEST.WA','interval':'1h','acquired_at':'2026-11-25T12:00:00+00:00',
                'price':.277,'currency':'PLN','price_matrix':matrix,'indicators':{},'ohlc':{},
                'previous_closed':{}}

    def test_legacy_anchor_cannot_claim_daily_change(self):
        snap=self.snapshot({'anchor_price':.265,'change_pct':4.5283018868})
        self.assertFalse(KI.daily_matrix_reference_ready(snap))
        contract=KI.price_change_contract(snap)
        self.assertEqual(contract['daily']['status'],'UNAVAILABLE')
        self.assertAlmostEqual(contract['tracking']['change_pct'],4.5283018868)

    def test_verified_previous_close_produces_negative_daily_return(self):
        snap=self.snapshot({'reference_status':'READY','reference_session':'2026-11-24',
            'session_date':'2026-11-25','anchor_price':.279,'anchor_at':'2026-11-24T16:00:00+01:00',
            'change_pct':(.277/.279-1)*100})
        contract=KI.price_change_contract(snap)
        self.assertEqual(contract['daily']['status'],'READY')
        self.assertEqual(contract['daily']['reference_session'],'2026-11-24')
        self.assertAlmostEqual(contract['daily']['reference_price'],.279)
        self.assertAlmostEqual(contract['daily']['change_pct'],-.7168458781)

    def test_ai_catalog_names_both_reference_and_daily_return(self):
        snap=self.snapshot({'reference_status':'READY','reference_session':'2026-11-24',
            'session_date':'2026-11-25','anchor_price':.279,'anchor_at':'2026-11-24T16:00:00+01:00',
            'change_pct':(.277/.279-1)*100})
        material={'daily_candles':[{'time':'2026-11-24T00:00:00+01:00','open':.28,'high':.282,
            'low':.278,'close':.279,'volume':1000}], 'sources':[]}
        facts=company_narrative.facts_for(snap,material)
        self.assertEqual(facts['quality.daily_reference_status']['value'],'READY')
        self.assertAlmostEqual(facts['daily.previous_close']['value'],.279)
        self.assertAlmostEqual(facts['daily.change_pct']['value'],-.7168458781)
        self.assertIn('technicznej',facts['tracking.change_pct']['label'])

    def test_same_fetch_close_wins_when_cached_daily_close_conflicts(self):
        snap={'ticker':'SZR.WA','acquired_at':'2026-11-26T12:29:40+00:00','price':.278,
              'corporate_actions':[],'chart_history':[{
                  'time':'2026-11-25T16:00:00+01:00','end':'2026-11-25T17:05:00+01:00',
                  'status':'CLOSED','close':.252}]}
        basis=market_intelligence.price_basis(snap,{
            'session_date':'2026-11-25','close':.240},snap['acquired_at'])
        self.assertEqual(basis['status'],'REFERENCE_SOURCE_CONFLICT')
        self.assertAlmostEqual(basis['cached_reference'],.240)
        self.assertAlmostEqual(basis['reference_override'],.252)
        self.assertAlmostEqual(basis['same_fetch_previous_close'],.252)

    def test_ai_accepts_proven_same_fetch_reference_but_not_conflicting_daily_row(self):
        matrix={'reference_status':'READY','reference_session':'2026-11-25',
                'session_date':'2026-11-26','anchor_price':.252,
                'anchor_at':'2026-11-25T17:05:00+01:00','change_pct':(.278/.252-1)*100,
                'reference_kind':'SAME_FETCH_PREVIOUS_SESSION_CLOSE'}
        snap={'ticker':'SZR.WA','interval':'1h','acquired_at':'2026-11-26T12:29:40+00:00',
              'price':.278,'currency':'PLN','price_matrix':matrix,'indicators':{},'ohlc':{},
              'previous_closed':{},'price_basis':{'status':'REFERENCE_SOURCE_CONFLICT',
              'same_fetch_previous_close':.252}}
        material={'daily_candles':[{'time':'2026-11-25T00:00:00+01:00','open':.218,
            'high':.244,'low':.19,'close':.24,'volume':2494234}], 'sources':[]}
        facts=company_narrative.facts_for(snap,material)
        self.assertEqual(facts['quality.daily_reference_status']['value'],'READY')
        self.assertAlmostEqual(facts['daily.previous_close']['value'],.252)
        self.assertAlmostEqual(facts['daily.change_pct']['value'],10.31746031746)


if __name__=='__main__':
    unittest.main()
