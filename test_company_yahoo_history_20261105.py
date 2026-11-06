import copy
from datetime import datetime, timedelta
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import KI
import company_market_history as market
import daily_analogs as daily
from test_daily_analogs_20261105 import NOW, history


class FixedDate(datetime):
    @classmethod
    def now(cls, tz=None):
        return NOW if tz else NOW.replace(tzinfo=None)


class CompanyYahooHistoryTests(unittest.TestCase):
    def test_52_weeks_only_with_previous_close_and_no_ki_observations(self):
        cache = history('HUMA')
        rows = market.market_rows(cache, NOW)
        cutoff = (NOW.astimezone(daily.zone('HUMA')).date() - timedelta(weeks=52)).isoformat()
        self.assertGreater(len(rows), 240)
        self.assertLess(len(rows), 270)
        self.assertTrue(all(r['session'] >= cutoff and r['ticker'] == 'HUMA' for r in rows))
        self.assertIsNotNone(rows[0]['previous_close'])
        self.assertTrue(all(datetime.fromisoformat(r['end']) <= NOW for r in rows))
        cache['rows'].append({**cache['rows'][-1], 'session': '2026-11-06', 'end': '2026-11-06T21:00:00+00:00'})
        self.assertEqual(len(market.market_rows(cache, NOW)), len(rows))
        self.assertEqual(market.market_rows({**cache, 'version': 'wrong'}, NOW), [])

    def test_colored_daily_cards_keep_ohlcv_and_split_notice(self):
        rows = market.market_rows(history('HUMA'), NOW)[-3:]
        for row, direction in zip(rows, ('up', 'down', 'flat')):
            row.update(daily_movement=direction, split=True)
        html = market.cards(rows)
        for direction in ('up', 'down', 'flat'):
            self.assertIn('class="ki-history-card daily-' + direction + '"', html)
        for label in ('Otwarcie', 'Maksimum', 'Minimum', 'Wolumen', 'USD', 'Yahoo', 'Split'):
            self.assertIn(label, html)

    def test_same_issuer_required_even_when_foreign_case_is_an_exact_match(self):
        cases = daily.build_cases(history('HUMA'), NOW)
        reference = cases[-1]
        old = copy.deepcopy(cases[-20])
        old['features'] = copy.deepcopy(reference['features'])
        foreign = {**copy.deepcopy(old), 'ticker': 'PLRX'}
        found = daily.find_matches(reference, [foreign, old, reference])
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]['case']['ticker'], 'HUMA')
        self.assertLess(found[0]['case']['session'], reference['session'])

    def test_show_history_downloads_once_and_pagination_never_calls_providers(self):
        from streamlit.testing.v1 import AppTest
        with tempfile.TemporaryDirectory() as folder:
            store = KI.Store(Path(folder) / 'history.sqlite3')
            script = ('from pathlib import Path\nimport KI, company_history\n'
                      f'company_history.render(KI.Store(Path({str(store.path)!r})))')
            with patch.object(market, 'datetime', FixedDate), patch.object(daily, 'datetime', FixedDate), \
                 patch.object(daily, 'download', return_value=history('HUMA')) as download, \
                 patch.object(KI, 'fetch_market', side_effect=AssertionError('No scanner fetch')):
                app = AppTest.from_string(script).run(timeout=30)
                download.assert_not_called()
                app.text_input(key='market_history_input').set_value(' huma ')
                next(b for b in app.button if b.label == 'Pokaż historię 52 tygodni').click().run(timeout=30)
                self.assertEqual(len(app.exception), 0)
                download.assert_called_once()
                self.assertEqual(app.number_input(key='market_history_page').value, 1)
                self.assertTrue(any('HUMA · Yahoo Finance' in c.value for c in app.caption))
                app.number_input(key='market_history_page').set_value(2).run(timeout=30)
                app.run(timeout=30)
                download.assert_called_once()
                self.assertEqual(daily.refresh(store, 'HUMA', NOW), 'CACHED')
                download.assert_called_once()
                next(b for b in app.button if b.label == 'Wyczyść').click().run(timeout=30)
                self.assertEqual(len(app.exception), 0)
                self.assertEqual(app.text_input(key='market_history_input').value, '')
            with store.connection() as db:
                for table in ('observations', 'daily_candles', 'events', 'analysis_jobs', 'outbox'):
                    self.assertEqual(db.execute('SELECT COUNT(*) FROM ' + table).fetchone()[0], 0)


if __name__ == '__main__':
    unittest.main()
