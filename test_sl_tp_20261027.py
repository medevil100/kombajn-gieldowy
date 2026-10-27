import copy
import unittest
from datetime import datetime,timedelta,timezone
import sl_tp
import KI
import test_alert_quality_20261026 as fixtures


class TradePlanTests(unittest.TestCase):
    def sample(self):
        now=datetime.now(timezone.utc);rows=[]
        # Repeated, distinct swing highs and lows with two neighbours each side.
        for n in range(30):
            low=8. if n in (4,14,24) else 9.
            high=12. if n==8 else 14. if n==18 else 11.
            start=now-timedelta(hours=31-n)
            rows.append({'time':start.isoformat(),'end':(start+timedelta(hours=1)).isoformat(),
                         'open':10.,'close':10.,'high':high,'low':low,'volume':100.,'status':'CLOSED'})
        return {'ticker':'AAA','interval':'1h','currency':'USD','price':10.,'acquired_at':now.isoformat(),
                'indicators':{'atr':1.},'chart_history':rows},now

    def test_levels_from_closed_swings_and_atr(self):
        s,now=self.sample();before=copy.deepcopy(s);p=sl_tp.build_plan(s,3,now)
        self.assertEqual(p['status'],'INDICATIVE');self.assertEqual(p['sl'],7.75)
        self.assertEqual((p['tp1'],p['tp2']),(12,14));self.assertAlmostEqual(p['rr1'],2/2.25)
        self.assertFalse(p['execution_confirmed']);self.assertEqual(before,s)

    def test_all_tickers_use_same_rules_and_spread_reduces_reward(self):
        s,now=self.sample();base=sl_tp.build_plan(s,3,now)
        for ticker in ('VCYT','ABC.WA','GNPX'):
            s.update(ticker=ticker,spread={'bid':9.8,'ask':10.2})
            p=sl_tp.build_plan(s,3,now)
            self.assertLess(p['rr1'],base['rr1']);self.assertEqual(p['entry'],10)

    def test_missing_stale_and_downward_data_cannot_form_plan(self):
        s,now=self.sample()
        for change in (None,0,-3):self.assertEqual(sl_tp.build_plan(s,change,now)['status'],'UNAVAILABLE')
        self.assertEqual(sl_tp.build_plan(s,3,now+timedelta(minutes=16))['status'],'UNAVAILABLE')
        s['indicators']={};self.assertEqual(sl_tp.build_plan(s,3,now)['status'],'UNAVAILABLE')

    def test_open_candles_cannot_create_targets(self):
        s,now=self.sample()
        s['chart_history'][18]['status']='OPEN'
        self.assertEqual(sl_tp.build_plan(s,3,now)['status'],'UNAVAILABLE')

    def test_quote_flag_without_timestamp_cannot_set_ask_entry(self):
        s,now=self.sample();s['spread']={'bid':9.9,'ask':10.1,'freshness_confirmed':True}
        self.assertEqual(sl_tp.build_plan(s,3,now)['entry'],10)
        s['spread']['acquired_at']=now.isoformat()
        self.assertEqual(sl_tp.build_plan(s,3,now)['entry'],10.1)

    def test_stored_plan_is_historical_after_validity(self):
        s,now=self.sample();p=sl_tp.build_plan(s,3,now)
        self.assertIn('zapis historyczny',sl_tp.plan_lines(p,now=now+timedelta(minutes=16))[0])

    def test_space_uses_last_price_and_support_not_stop(self):
        s,now=self.sample();p=sl_tp.build_plan(s,3,now)
        self.assertEqual(p['support_distance_pct'],20)
        self.assertEqual(p['resistance_distance_pct'],20)
        line=sl_tp.movement_space_line(p)
        self.assertIn('Wsparcie 8,0000',line);self.assertIn('do wsparcia −20,00%',line)
        self.assertIn('do oporu +20,00%',line)
        self.assertNotIn('7,7500',line)

    def test_plan_is_in_pre_ai_package_and_telegram(self):
        ev,result=fixtures.AlertQualityTests().sample();s,now=self.sample()
        s['indicators']={**ev['snapshot']['indicators'],**s['indicators']}
        ev['snapshot'].update(s);ev['snapshot']['price_matrix']={'change_pct':3}
        ctx={'sources':[]};manifest=KI.build_analysis_manifest(ev,ctx)
        self.assertEqual(manifest['trade_plan']['status'],'INDICATIVE')
        result['assessment']={'movement':'Wzrost ma mieszane wskazania.', 'activity':'Wolumen świecy jest częściowy.',
                              'risk':'Brak ofert ogranicza ocenę wykonania, potencjał jest mniejszy od ryzyka.'}
        ctx['analysis_manifest']=manifest
        self.assertIn('SL/TP orientacyjnie: SL',KI.opportunity_message('e',ev,ctx,result))


if __name__=='__main__':unittest.main()
