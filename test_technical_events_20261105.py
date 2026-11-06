import copy
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import KI
import technical_events as events


def snapshot():
    start = datetime(2026, 10, 26, 8, tzinfo=timezone.utc)
    rows = [{'time': (start + timedelta(hours=i)).isoformat(),
             'end': (start + timedelta(hours=i + 1)).isoformat(),
             'open': 100., 'high': 101., 'low': 99., 'close': 100., 'volume': 1000.,
             'status': 'CLOSED'} for i in range(60)]
    rows[-1].update(open=100., high=122., low=100., close=120.)
    now = start + timedelta(hours=60)
    result = KI.opportunity_test_snapshot(now, 'AAA', price=120.)
    result.update(currency='USD', chart_history=KI.build_chart_history(rows))
    return result


class TechnicalEventsTests(unittest.TestCase):
    def test_breakout_and_crossovers_use_closed_history_and_leave_input_untouched(self):
        current = snapshot()
        original = copy.deepcopy(current)
        view = events.analyze(current)
        codes = {event['code'] for event in view['events']}
        self.assertTrue({'RESISTANCE_BREAKOUT', 'SMA_CROSS_UP', 'MACD_CROSS_UP'} <= codes)
        self.assertEqual(current, original)
        self.assertEqual(view['candle_time'], current['chart_history'][-1]['time'])

    def test_open_or_future_candle_cannot_create_an_event(self):
        current = snapshot()
        current['chart_history'][-1]['status'] = 'OPEN'
        self.assertNotIn('RESISTANCE_BREAKOUT', {e['code'] for e in events.analyze(current)['events']})
        current['chart_history'][-1]['status'] = 'CLOSED'
        current['acquired_at'] = current['chart_history'][-1]['time']
        self.assertNotIn('RESISTANCE_BREAKOUT', {e['code'] for e in events.analyze(current)['events']})

    def test_missing_or_carried_reference_cannot_prove_breakout(self):
        for change in ({'close': None}, {'price_origin': 'carried_previous_close'}):
            current = snapshot()
            current['chart_history'][-10].update(change)
            view = events.analyze(current)
            self.assertNotIn('RESISTANCE_BREAKOUT', {e['code'] for e in view['events']})
            self.assertTrue(view['missing'])

    def test_downward_events_keep_their_direction(self):
        current = snapshot()
        last = current['chart_history'][-1]
        last.update(open=100., high=100., low=78., close=80., macd=-1., macd_signal=0.)
        codes = {event['code']: event for event in events.analyze(current)['events']}
        self.assertEqual(codes['SUPPORT_BREAKDOWN']['direction'], 'DOWN')
        self.assertEqual(codes['SMA_CROSS_DOWN']['direction'], 'DOWN')
        self.assertEqual(codes['MACD_CROSS_DOWN']['direction'], 'DOWN')

    def test_bollinger_compares_with_previous_widths_and_body_pattern_is_independent(self):
        current = snapshot()
        for row in current['chart_history']:
            row.update(bb_upper=110., bb_lower=90., bb_middle=100.)
        current['chart_history'][-1].update(bb_upper=104., bb_lower=96., bb_middle=100.)
        codes = {event['code'] for event in events.analyze(current)['events']}
        self.assertIn('BB_SQUEEZE', codes)
        previous, last = current['chart_history'][-2:]
        previous.update(open=101., close=100., high=102., low=99.)
        last.update(open=99., close=102., high=103., low=98.)
        self.assertIn('BULLISH_ENGULFING', {e['code'] for e in events.analyze(current)['events']})

    def test_mobile_markup_limits_chips_and_escapes_details(self):
        view = events.analyze(snapshot())
        view['events'] += [
            {'code': 'DOJI', 'label': '<script>Doji</script>', 'direction': 'NEUTRAL',
             'role': 'WARNING', 'evidence': '<img src=x>'}
        ]
        markup = events.cards_html(view)
        self.assertEqual(markup.count('<span class="ki-event-chip '), 3)
        self.assertIn('+1 w szczegółach', markup)
        self.assertNotIn('<script>', markup)
        self.assertIn('&lt;script&gt;', markup)
        self.assertIn('flex-wrap:wrap', markup)
        self.assertIn('min-height:44px', markup)

    def test_confirmation_saves_event_context_once_and_outcome_filter_renders(self):
        from streamlit.testing.v1 import AppTest
        current = snapshot()
        now = current['acquired_at']
        matrix = {'newly_confirmed': True, 'activity_verified': True, 'anchor_price': 110.,
                  'change_pct': 9., 'state': 'CONFIRMED'}
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'events.sqlite3'
            store = KI.Store(path)
            with patch.object(KI, '_record_price_matrix_read', return_value=matrix):
                KI.detect_market(store, current, {'price_matrix_enabled': True})
                changed = {**current, 'chart_history': []}
                KI.detect_market(store, changed, {'price_matrix_enabled': True})
            with store.connection() as connection:
                raw = connection.execute('SELECT payload FROM signal_technical_context').fetchone()[0]
            self.assertIn('RESISTANCE_BREAKOUT', {e['code'] for e in json.loads(raw)['events']})
            rows = KI.signal_session_outcomes(store, '2026-11-05T18:00:00+00:00')
            self.assertEqual(rows[0]['technical_events']['method'], events.METHOD)
            script = ('from pathlib import Path\nimport KI\n'
                      f'KI.render_signal_outcomes(KI.Store(Path({str(path)!r})))')
            app = AppTest.from_string(script).run(timeout=30)
            self.assertEqual(len(app.exception), 0)
            app.selectbox(key='outcome_event_type').set_value('Wybicie oporu').run(timeout=30)
            self.assertEqual(len(app.exception), 0)
            self.assertTrue(all('Wybicie oporu' in value for value in app.dataframe[1].value['Rodzaj zdarzenia']))


if __name__ == '__main__':
    unittest.main()
