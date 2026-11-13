import copy
from datetime import datetime, timedelta, timezone
import unittest
from unittest.mock import patch

import indicator_view as view


class IndicatorViewTests(unittest.TestCase):
    def test_historical_tone_is_inline_not_only_stylesheet(self):
        self.setUp()
        self.s['acquired_at']=(self.now-timedelta(days=2)).isoformat()
        html=view.render_html(self.s,[{'Wskaźnik':'SMA 10','Wartość':'1,3996 USD'}],now=self.now)
        self.assertIn('<strong style="color:#68dfaa">',html)
        self.assertIn('Zapis historyczny',html)

    def setUp(self):
        self.now=datetime(2026,11,11,16,tzinfo=timezone.utc)
        self.s={'price':1.4,'currency':'USD','acquired_at':self.now.isoformat(),'candle_status':'OPEN',
                'indicators':{'ma_fast':1.3996,'last_upper_bb':1.4984,'bb_sma':1.4108,'last_lower_bb':1.3232,
                              'last_macd':-.0045,'last_macd_signal':.0016,'last_macd_hist':-.0061,
                              'plus_di':19.98,'minus_di':30.29,'adx':14.36,'rsi':44.51,'atr':.0552,'obv':-497714,'rvol':1.54},
                'supplemental_indicators':{'vwap':1.3944,'stoch_rsi_k':24.7,'fibonacci':[1.53,1.4828,1.4536,1.43,1.4064,1.3728,1.33]}}

    def describe(self,key):return view.describe(key,view.values(self.s),self.s)

    def test_price_relative_levels_and_equality(self):
        self.assertEqual(self.describe('ma_fast')[0],'up')
        self.assertEqual(self.describe('fib_0')[0],'down')
        self.assertEqual(self.describe('vwap')[0],'up')
        self.s['price']=1.3996
        self.assertEqual(self.describe('ma_fast')[0],'attention')

    def test_bollinger_location_not_buy_sell(self):
        for price,phrase in ((1.2,'poniżej dolnej'),(1.4,'między dolną'),(1.4108,'na środku'),(1.45,'między środkiem'),(1.6,'powyżej górnej')):
            self.s['price']=price
            result=view.bollinger(self.s,view.values(self.s))
            self.assertIn(phrase,result)
            self.assertNotIn('Kup',result)
            self.assertNotIn('Sprzedaj',result)
        self.assertIn('--ki-pos:100.0000%',result)
        self.s['indicators']['last_lower_bb']=1.5
        self.assertIn('brak kompletu',view.bollinger(self.s,view.values(self.s)))

    def test_missing_invalid_values_never_green(self):
        for value in (None,False,float('nan'),float('inf'),'1.4',0):
            self.s['price']=value
            self.assertEqual(self.describe('ma_fast')[0],'neutral')
        self.s['indicators']['rsi']=101
        self.assertIsNone(self.describe('rsi')[2])

    def test_neutral_measures_and_direction_relations(self):
        for key in ('adx','atr','obv','rsi'):self.assertEqual(self.describe(key)[0],'neutral')
        for key in ('last_macd','last_macd_signal','last_macd_hist','plus_di','minus_di'):
            self.assertEqual(self.describe(key)[0],'down')
        self.assertIn('bez oceny przecięcia',self.describe('last_macd')[1])
        self.assertIn('3,94%',self.describe('atr')[1])

    def test_oscillator_extremes_are_attention_not_trade_direction(self):
        for value in (10,90):
            self.s['indicators']['rsi']=value
            self.assertEqual(self.describe('rsi')[0],'attention')
        self.assertEqual(self.describe('stoch_rsi_k')[2],24.7)

    def test_volume_never_implies_bullish_and_keeps_partial(self):
        self.assertEqual(self.describe('rvol')[0],'attention')
        self.assertIn('częściowy',self.describe('rvol')[1])
        self.s['partial_interval']=True
        self.assertIn('Skrócona',self.describe('rvol')[1])

    def test_future_missing_timestamps_neutral(self):
        rows=[{'Wskaźnik':'SMA 10','Wartość':'1,3996 USD'}]
        for stamp in (None,(self.now+timedelta(minutes=1)).isoformat(),'2026-11-11T16:00:00'):
            self.s['acquired_at']=stamp
            html=view.render_html(self.s,rows,self.now)
            self.assertIn('oznaczenia neutralne',html)
            self.assertNotIn('--ki-tone:#68dfaa',html)
            self.assertIn('Cena powyżej',html)

    def test_historical_report_preserves_colors_with_explicit_timestamp(self):
        self.s['acquired_at']=(self.now-timedelta(days=1)).isoformat()
        rows=[{'Wskaźnik':'SMA 10','Wartość':'1,3996 USD'},
              {'Wskaźnik':'Histogram MACD','Wartość':'-0,0061 USD'}]
        html=view.render_html(self.s,rows,self.now)
        self.assertIn('Zapis historyczny',html)
        self.assertIn('nie aktualny rynek',html)
        self.assertIn(self.s['acquired_at'],html)
        self.assertIn('--ki-tone:#68dfaa',html)
        self.assertIn('--ki-tone:#ff929b',html)

    def test_escape_and_no_mutation(self):
        self.s['currency']='<script>bad()</script>'
        rows=[{'Wskaźnik':'<img src=x onerror=bad()>','Wartość':'<b>5</b>','Znaczenie':'<svg>'}]
        before=copy.deepcopy((self.s,rows))
        html=view.render_html(self.s,rows,self.now)
        self.assertNotIn('<script>',html)
        self.assertIn('&lt;b&gt;',html)
        self.assertEqual((self.s,rows),before)
        self.assertIn('@media(max-width:600px)',html)

    def test_shared_renderer_keeps_payload_contract_and_all_values(self):
        import KI
        before=copy.deepcopy(self.s)
        rows=KI.opportunity_indicator_rows(self.s)
        result=KI.indicator_table_html(self.s)
        for row in rows:
            self.assertIn(view.escape(row['Wskaźnik']),result)
            self.assertIn(view.escape(row['Wartość']),result)
            self.assertEqual(set(row),{'Wskaźnik','Wartość'})
        self.assertEqual(before,self.s)

    def test_streamlit_wrapper_no_exceptions(self):
        from streamlit.testing.v1 import AppTest
        def app():
            import KI
            KI.render_indicator_table({'price':1.4,'indicators':{'rsi':44.51}})
        app=AppTest.from_function(app).run()
        self.assertFalse(app.exception)
        self.assertIn('RSI',app.markdown[0].value)


if __name__=='__main__':unittest.main()
