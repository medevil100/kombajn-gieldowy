import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import KI
import portfolio_view
import tracking_view
import test_sl_tp_20261027 as plan_fixtures


class PortfolioCardsTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/'portfolio.sqlite3'
        self.store=KI.Store(self.path)
        self.config=[{'ticker':'AAA','sl':1.2,'tp':2.5,'direction':'long',
                      'sl_fired_at':'2026-10-28T12:00:00Z','tp_fired_at':None},
                     {'ticker':'BBB.WA','sl':None,'tp':None,'direction':'long',
                      'sl_fired_at':None,'tp_fired_at':None}]
        KI.portfolio_save(self.store,self.config)
        snapshot=KI.opportunity_test_snapshot(datetime.now(timezone.utc),'AAA',price=2.)
        snapshot['spread']={'bid':1.99,'ask':2.01,'spread_pct':1.,'freshness_confirmed':False}
        snapshot['trade_plan']={'sl':999.,'tp1':9999.}
        with self.store.transaction() as c:
            c.execute('INSERT INTO observations(ticker,interval,candle_time,acquired_at,candle_status,payload) VALUES(?,?,?,?,?,?)',
                ('AAA','1h',snapshot['candle_time'],snapshot['acquired_at'],snapshot['candle_status'],json.dumps(snapshot)))

    def app(self):
        from streamlit.testing.v1 import AppTest
        script='import KI\nfrom pathlib import Path\nKI.render_portfolio(KI.Store(Path('+repr(str(self.path))+')))'
        return AppTest.from_string(script).run(timeout=30)

    def test_saved_fx_rate_does_not_hide_portfolio(self):
        with self.store.transaction() as c:
            c.execute('INSERT INTO runtime VALUES(?,?,?)', ('portfolio_usd_pln', json.dumps({'rate': 4.1234, 'effective_date': '2026-11-20'}), '2026-11-20T12:00:00+00:00'))
        app = self.app()
        self.assertEqual(len(app.exception), 0)
        self.assertTrue(any('USD/PLN: 4,1234' in item.value for item in app.get('caption')))
        self.assertEqual([row['Ticker'] for row in app.dataframe[0].value.to_dict('records')], ['AAA', 'BBB.WA'])

    def test_render_and_refresh_are_read_only_and_call_no_providers(self):
        with self.store.connection() as c:before=list(c.iterdump())
        with patch.object(KI,'fetch_market',side_effect=AssertionError('network')),patch.object(KI,'service_http',side_effect=AssertionError('provider')):
            app=self.app()
            self.assertEqual(len(app.exception),0)
            app.button(key='portfolio_refresh').click().run(timeout=30)
            self.assertEqual(len(app.exception),0)
        self.assertEqual(KI.portfolio_get(self.store),self.config)
        with self.store.connection() as c:self.assertEqual(before,list(c.iterdump()))

    def test_card_ai_trigger_runs_selected_ticker_and_renders_result_in_portfolio(self):
        with (patch.object(portfolio_view,'interactive_cards',return_value=SimpleNamespace(ai='AAA')),
              patch.object(KI.radar_ai,'run_manual_portfolio',return_value='DONE') as run_ai,
              patch.object(KI.radar_ai,'render_latest') as render_result):
            app=self.app()
        self.assertEqual(len(app.exception),0)
        self.assertEqual(run_ai.call_count,1)
        self.assertEqual(run_ai.call_args.args[-1],'AAA')
        self.assertEqual(render_result.call_count,1)
        rendered_store,rendered_ticker=render_result.call_args.args
        self.assertEqual(rendered_store.path,self.store.path)
        self.assertEqual(rendered_ticker,'AAA')

    def test_existing_threshold_editor_preserves_alert_history(self):
        app=self.app()
        app.number_input(key='sl_AAA').set_value(1.3)
        app.number_input(key='tp_AAA').set_value(2.8)
        app.button(key='portfolio_save_thresholds').click().run(timeout=30)
        self.assertEqual(len(app.exception),0)
        saved=KI.portfolio_get(self.store)
        self.assertEqual((saved[0]['sl'],saved[0]['tp']),(1.3,2.8))
        self.assertEqual(saved[0]['sl_fired_at'],self.config[0]['sl_fired_at'])
        self.assertIsNone(saved[0]['tp_fired_at'])

    def test_market_filter_changes_cards_and_tables_only(self):
        with self.store.connection() as c:
            before = list(c.iterdump())
        with patch.object(portfolio_view, 'cards_html', wraps=portfolio_view.cards_html) as render:
            app = self.app()
            self.assertEqual(app.radio(key='portfolio_market').value, 'Wszystkie')
            for market, expected in (('GPW', ['BBB.WA']), ('USA', ['AAA']),
                                     ('Wszystkie', ['AAA', 'BBB.WA'])):
                app.radio(key='portfolio_market').set_value(market).run(timeout=30)
                self.assertEqual(len(app.exception), 0)
                rendered = [row['Ticker'] for row in render.call_args_list[-1].args[0]]
                self.assertEqual(rendered, expected)
                self.assertEqual(app.dataframe[0].value['Ticker'].tolist(), expected)
                self.assertEqual(app.number_input(key='sl_AAA').value, 1.2)
        with self.store.connection() as c:
            self.assertEqual(list(c.iterdump()), before)

    def test_market_filter_handles_empty_group(self):
        KI.portfolio_save(self.store, self.config[:1])
        app = self.app()
        app.radio(key='portfolio_market').set_value('GPW').run(timeout=30)
        self.assertEqual(len(app.exception), 0)
        self.assertIn('Brak spółek z rynku GPW w portfelu.', [item.value for item in app.info])
        self.assertEqual(len(app.dataframe), 0)
        app.radio(key='portfolio_market').set_value('USA').run(timeout=30)
        self.assertEqual(app.dataframe[0].value['Ticker'].tolist(), ['AAA'])

    def test_existing_add_and_delete_actions_still_work(self):
        app=self.app()
        app.text_input(key='portfolio_add').set_value('CCC')
        app.button(key='portfolio_add_btn').click().run(timeout=30)
        self.assertEqual(len(app.exception),0)
        self.assertEqual(KI.portfolio_tickers(self.store),['AAA','BBB.WA','CCC'])
        self.assertEqual(KI.portfolio_get(self.store)[0],self.config[0])
        app.button(key='portfolio_del_CCC').click().run(timeout=30)
        self.assertEqual(len(app.exception),0)
        self.assertEqual(KI.portfolio_tickers(self.store),['AAA','BBB.WA'])

    def test_position_metrics_keep_native_and_pln_currency_results_separate(self):
        usd=KI.portfolio_position_metrics({'shares':10,'entry_price':4.,'entry_currency':'USD',
                                           'entry_fx_pln':4.,'valuation_fx_pln':4.2},5.,'USD')
        self.assertTrue(usd['ready'])
        self.assertEqual((usd['cost_native'],usd['value_native'],usd['pnl_native']),(40.,50.,10.))
        self.assertEqual((usd['cost_pln'],usd['value_pln'],usd['pnl_pln']),(160.,210.,50.))
        pln=KI.portfolio_position_metrics({'shares':100,'entry_price':2.,'entry_currency':'PLN'},1.5,'PLN')
        self.assertEqual((pln['cost_pln'],pln['value_pln'],pln['pnl_pln']),(200.,150.,-50.))

    def test_shared_nbp_rate_is_cached_and_failure_preserves_previous_rate(self):
        import io
        from urllib.error import URLError
        now=datetime(2026,11,23,8,tzinfo=timezone.utc)
        body=b'{"rates":[{"effectiveDate":"2026-11-20","mid":4.12}]}'
        with patch('urllib.request.urlopen',return_value=io.BytesIO(body)) as provider:
            first=KI.refresh_portfolio_usd_pln(self.store,now)
            second=KI.refresh_portfolio_usd_pln(self.store,now+timedelta(hours=1))
            self.assertEqual(provider.call_count,1)
        self.assertEqual((first['rate'],first['effective_date']),(4.12,'2026-11-20'))
        self.assertEqual(second['rate'],4.12)
        with patch('urllib.request.urlopen',side_effect=URLError('offline')):
            failed=KI.refresh_portfolio_usd_pln(self.store,now+timedelta(days=1))
        self.assertEqual((failed['rate'],failed['effective_date']),(4.12,'2026-11-20'))
        self.assertEqual(failed['error'],'URLError')

    def test_position_editor_preserves_existing_alert_thresholds(self):
        app=self.app()
        app.number_input(key='portfolio_shares_AAA').set_value(20.)
        app.number_input(key='portfolio_entry_AAA').set_value(1.5)
        app.button(key='portfolio_save_positions').click().run(timeout=30)
        saved=KI.portfolio_get(self.store)[0]
        self.assertEqual((saved['shares'],saved['entry_price'],saved['sl'],saved['tp']),(20.,1.5,1.2,2.5))

    def test_cards_show_manual_levels_status_and_last_acquisition(self):
        row={'Ticker':'AAA','Cena':'2,0000 USD','Zmiana 1H':'+1,00%',
             'SL':'1,2000','TP':'2,5000','SL status':'FIRED','TP status':'armed',
             '_fresh':True,'_acquired_at':'2026-10-29T12:00:00Z'}
        markup=portfolio_view.cards_html([row])
        for expected in ('SL · Twój próg','TP · Twój próg','1,2000','2,5000','Wyzwolony','Ustawiony','13:00:00 CET'):
            self.assertIn(expected,markup)
        self.assertIn('nie są wyliczonym planem technicznym',markup)

    def test_missing_price_keeps_manual_thresholds_without_fake_freshness(self):
        app=self.app()
        self.assertEqual(len(app.exception),0)
        # A missing observation cannot remove or replace user thresholds.
        self.assertEqual(app.number_input(key='sl_AAA').value,1.2)
        self.assertEqual(app.number_input(key='sl_BBB.WA').value,0.)
        markup=portfolio_view.cards_html([{'Ticker':'AAA','Cena':'brak odczytu','SL':'1,2000','SL status':'armed','_fresh':False}])
        self.assertIn('brak odczytu',markup)
        self.assertIn('1,2000',markup)
        self.assertIn('Dane historyczne lub niepełne',markup)
        self.assertIn('Nie ustawiono',markup)

    def test_card_text_is_escaped_and_risk_is_explicitly_archival(self):
        markup=portfolio_view.cards_html([{'Ticker':'<script>alert(1)</script>','Powody':'<img src=x onerror=alert(1)>','_fresh':False}])
        self.assertNotIn('<script>',markup)
        self.assertNotIn('<img',markup)
        self.assertIn('&lt;script&gt;',markup)
        self.assertIn('Ryzyko z zapisanej analizy',markup)

    def test_manual_thresholds_and_automatic_plan_are_in_separate_sections(self):
        snapshot,now=plan_fixtures.TradePlanTests().sample()
        row={'Ticker':'AAA','SL':'1,2000','TP':'2,5000','SL status':'armed','TP status':'armed',
             '_currency':'USD','_analysis_levels':tracking_view.level_view(snapshot,3,now)}
        markup=portfolio_view.cards_html([row])
        manual,analysis=markup.split('Poziomy z analizy KI',1)
        self.assertIn('Moje progi alertów',manual)
        self.assertIn('1,2000',manual)
        self.assertNotIn('7,7500',manual)
        for value in ('7,7500 USD','12,0000 USD','14,0000 USD','Wsparcie','Opór','TP1','TP2','Dane analizy'):
            self.assertIn(value,analysis)
        self.assertEqual(row['SL'],'1,2000')
        self.assertEqual(row['TP'],'2,5000')

    def test_analysis_missing_or_historical_is_visible_without_changing_manual_values(self):
        snapshot,now=plan_fixtures.TradePlanTests().sample()
        view=tracking_view.level_view(snapshot,3,now+timedelta(minutes=20))
        markup=portfolio_view.cards_html([{'Ticker':'AAA','SL':'1,2000','_analysis_levels':view}])
        self.assertIn('Dane historyczne',markup)
        self.assertIn('7,7500',markup)
        snapshot['indicators']={}
        view=tracking_view.level_view(snapshot,3,now)
        markup=portfolio_view.cards_html([{'Ticker':'AAA','SL':'1,2000','_analysis_levels':view}])
        self.assertIn('Brak poprawnego ATR',markup)
        self.assertIn('1,2000',markup)
        self.assertNotIn('7,7500',markup)

    def test_render_computes_same_local_plan_without_writing_thresholds(self):
        snapshot,now=plan_fixtures.TradePlanTests().sample()
        start=now.replace(minute=0,second=0,microsecond=0)
        snapshot.update(candle_time=start.isoformat(),candle_end=(start+timedelta(hours=1)).isoformat(),
                        candle_status='OPEN',price_matrix={'change_pct':3.,'anchor_price':9.7})
        with self.store.transaction() as c:
            c.execute('INSERT INTO observations(ticker,interval,candle_time,acquired_at,candle_status,payload) VALUES(?,?,?,?,?,?)',
                ('AAA','1h',snapshot['candle_time'],snapshot['acquired_at'],'OPEN',json.dumps(snapshot)))
        with self.store.connection() as c:before=list(c.iterdump())
        original=portfolio_view.interactive_cards
        with patch.object(portfolio_view,'interactive_cards',side_effect=original) as renderer,patch.object(KI,'service_http',side_effect=AssertionError('paid request')):
            app=self.app()
            self.assertEqual(len(app.exception),0)
            self.assertEqual(renderer.call_count,1)
            rendered_rows=renderer.call_args.args[0]
            row=next(item for item in rendered_rows if item['Ticker']=='AAA')
        self.assertEqual(row['_analysis_levels']['plan']['sl'],7.75)
        self.assertEqual(row['SL'],'1,2000')
        self.assertEqual(row['TP'],'2,5000')
        markup=portfolio_view.cards_html([row])
        self.assertIn('data-ai-ticker="AAA"',markup)
        self.assertNotIn('href=',markup)
        self.assertEqual(KI.portfolio_get(self.store),self.config)
        with self.store.connection() as c:self.assertEqual(before,list(c.iterdump()))


if __name__=='__main__':unittest.main()
