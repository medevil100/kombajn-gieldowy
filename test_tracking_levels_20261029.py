import copy
import json
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

import KI
import tracking_view
import test_sl_tp_20261027 as fixtures


class TrackingLevelsTests(unittest.TestCase):
    def sample(self):
        snapshot, now = fixtures.TradePlanTests().sample()
        start = now.replace(minute=0, second=0, microsecond=0)
        snapshot.update(candle_time=start.isoformat(), candle_end=(start+timedelta(hours=1)).isoformat(),
                        candle_status='OPEN', price_matrix={'change_pct':3., 'anchor_price':9.7})
        return snapshot, now

    def test_complete_plan_shows_five_levels_without_mutating_source(self):
        snapshot, now = self.sample()
        original = copy.deepcopy(snapshot)
        view = tracking_view.level_view(snapshot, 3, now)
        values = tracking_view.level_values({'levels':view})
        self.assertTrue(view['fresh'])
        self.assertEqual(values, {'Wsparcie':8., 'Opór':12., 'SL':7.75, 'TP1':12., 'TP2':14.})
        self.assertEqual(snapshot, original)

    def test_closed_candle_or_expired_acquisition_is_explicitly_historical(self):
        snapshot, now = self.sample()
        expired = tracking_view.level_view(snapshot, 3, now+timedelta(minutes=16))
        self.assertFalse(expired['fresh'])
        self.assertIn('historyczne', expired['label'])
        self.assertEqual(expired['plan']['sl'],7.75)
        snapshot['candle_status']='CLOSED'
        closed = tracking_view.level_view(snapshot, 3, now)
        self.assertFalse(closed['fresh'])

    def test_decline_preserves_technical_levels_without_inventing_short_sl_tp(self):
        snapshot, now = self.sample()
        view = tracking_view.level_view(snapshot, -3, now)
        values = tracking_view.level_values({'levels':view})
        self.assertEqual(values['Wsparcie'],8.)
        self.assertEqual(values['Opór'],12.)
        self.assertIsNone(values['SL'])
        self.assertIsNone(values['TP1'])
        self.assertIsNone(values['TP2'])

    def test_missing_atr_or_reference_cannot_produce_a_complete_trade_plan(self):
        snapshot, now = self.sample()
        for ready in (True,False):
            current = copy.deepcopy(snapshot)
            if ready:current['indicators']={}
            view=tracking_view.level_view(current,3,now,reference_ready=ready)
            self.assertIsNone(tracking_view.level_values({'levels':view})['SL'])
            self.assertEqual(tracking_view.level_values({'levels':view})['Wsparcie'],8.)
        snapshot['chart_history']=[]
        view=tracking_view.level_view(snapshot,3,now)
        self.assertTrue(all(v is None for v in tracking_view.level_values({'levels':view}).values()))

    def test_future_or_missing_timestamp_does_not_reconstruct_a_plan(self):
        snapshot, now = self.sample()
        for at in (None,(now+timedelta(minutes=5)).isoformat()):
            snapshot['acquired_at']=at
            view=tracking_view.level_view(snapshot,3,now)
            self.assertEqual(view['plan']['status'],'UNAVAILABLE')
            self.assertFalse(view['fresh'])

    def seed(self,store,snapshot,now):
        original=copy.deepcopy(snapshot)
        original.update(price=9.,acquired_at=(now-timedelta(days=1)).isoformat())
        original['price_matrix']={'anchor_price':8.,'change_pct':3.}
        with store.transaction() as connection:
            connection.execute('INSERT INTO opportunities VALUES(?,?,?,?,?,?,?,?,?)',
                ('seq','AAA',snapshot['candle_time'],snapshot['candle_end'],'SELECTED','cycle',
                 json.dumps({'snapshot':original}),now.isoformat(),now.isoformat()))
            connection.execute('INSERT INTO observations(ticker,interval,candle_time,acquired_at,candle_status,payload) VALUES(?,?,?,?,?,?)',
                ('AAA','1h',snapshot['candle_time'],snapshot['acquired_at'],'OPEN',json.dumps(snapshot)))

    def test_tracking_uses_latest_snapshot_and_is_read_only_without_providers(self):
        snapshot, now=self.sample()
        with tempfile.TemporaryDirectory() as folder:
            store=KI.Store(Path(folder)/'test.sqlite3');self.seed(store,snapshot,now)
            with store.connection() as connection:before=list(connection.iterdump())
            with patch.object(KI,'fetch_market',side_effect=AssertionError('network')),patch.object(KI,'service_http',side_effect=AssertionError('paid call')):
                rows=KI.tracking_confirmed_opportunities(store,now=now)
            self.assertEqual(rows[0]['current_price'],10.)
            self.assertEqual(rows[0]['anchor_price'],8.)
            self.assertEqual(rows[0]['levels']['plan']['reference_price'],10.)
            self.assertEqual(rows[0]['levels']['plan']['sl'],7.75)
            with store.connection() as connection:self.assertEqual(before,list(connection.iterdump()))

    def test_card_escapes_stored_text_and_exposes_times_and_level_labels(self):
        snapshot,now=self.sample()
        row={'ticker':'<script>alert(1)</script>','levels':tracking_view.level_view(snapshot,3,now),
             'currency':'USD','current_price':10.,'anchor_price':8.,'change_pct':25.,
             'current_at':now.isoformat(),'confirmed_at':now.isoformat()}
        markup=tracking_view.cards_html([row])
        self.assertNotIn('<script>',markup)
        self.assertIn('&lt;script&gt;',markup)
        for label in ('Wsparcie','Opór','SL','TP1','TP2','Odczyt ceny','Dane poziomów'):
            self.assertIn(label,markup)

    def test_panel_renders_cards_and_filter_without_exception(self):
        from streamlit.testing.v1 import AppTest
        snapshot,now=self.sample()
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'test.sqlite3';store=KI.Store(path);self.seed(store,snapshot,now)
            script="import KI\nfrom pathlib import Path\nKI.render_confirmed_tracking(KI.Store(Path("+repr(str(path))+")))"
            app=AppTest.from_string(script).run(timeout=30)
            self.assertEqual(len(app.exception),0)
            self.assertEqual(app.selectbox[0].options,['Wszystkie','AAA'])
            app.selectbox[0].select('AAA').run(timeout=30)
            self.assertEqual(len(app.exception),0)


if __name__=='__main__':unittest.main()
