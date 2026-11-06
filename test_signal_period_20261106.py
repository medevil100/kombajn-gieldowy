import copy
from datetime import date
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import KI
import daily_analogs as daily
import signal_period_view as view
from company_market_history import market_rows
from test_daily_analogs_20261105 import NOW, history
from test_company_yahoo_history_20261105 import FixedDate


class SignalPeriodTests(unittest.TestCase):
    def test_full_year_is_available_and_start_filters_only_the_selected_period(self):
        cache = history('HUMA')
        rows = market_rows(cache, NOW)
        self.assertGreater(len(rows), 240)
        self.assertLess(rows[0]['session'], '2025-12-01')
        self.assertGreater(rows[-1]['session'], '2026-11-01')
        selected = [r for r in rows if r['session'] >= '2026-08-01']
        summary = view.period_summary(selected)
        self.assertEqual(summary['sessions'], len(selected))
        self.assertGreaterEqual(summary['from'], '2026-08-01')
        self.assertEqual(summary['to'], rows[-1]['session'])
        months = view.month_summaries(selected, [])
        self.assertEqual([r['month'] for r in months], ['2026-08', '2026-09', '2026-10', '2026-11'])
        self.assertEqual(sum(r['sessions'] for r in months), len(selected))
        self.assertEqual(view.period_summary([]), None)

    def test_split_does_not_fabricate_a_return_and_mixed_issuers_are_rejected(self):
        rows = market_rows(history('HUMA'), NOW)[-10:]
        rows[2]['split'] = True
        summary = view.period_summary(rows)
        self.assertIsNone(summary['change'])
        self.assertTrue(summary['split'])
        mixed = copy.deepcopy(rows)
        mixed[-1]['ticker'] = 'PLRX'
        with self.assertRaises(ValueError):
            view.period_summary(mixed)

    def test_event_outcomes_stop_at_selected_end_and_other_issuers_never_enter(self):
        cache = history('HUMA')
        rows = market_rows(cache, NOW)
        cases = daily.build_cases(cache, NOW)
        selected = rows[-20:-10]
        case = copy.deepcopy(next(c for c in cases if c['session'] == selected[-1]['session']))
        case['events'] = [{'code': 'X', 'label': 'Zdarzenie'}] * 2
        for row in case['outcomes'].values():
            row.update(change=999., status='Obliczono')
        foreign = copy.deepcopy(case)
        foreign.update(ticker='PLRX', session=selected[0]['session'])
        summary = view.event_review(selected, [case, foreign])
        self.assertEqual(summary[0]['count'], 1)
        self.assertTrue(all(r['n'] == 0 and r['mean'] is None for r in summary[0]['outcomes'].values()))

    def test_month_cards_escape_text_and_expose_comparable_values(self):
        months = view.month_summaries(market_rows(history('HUMA'), NOW)[-30:], [])
        months[0]['events'] = [{'label': '<script>unsafe</script>', 'count': 1}]
        html = view.months_html(months)
        for expected in ('Zamknięcie pierwszej sesji', 'Zamknięcie ostatniej sesji', 'Wolumen łącznie',
                         '@media(max-width:640px)', 'USD'):
            self.assertIn(expected, html)
        self.assertNotIn('<script>', html)
        self.assertIn('&lt;script&gt;', html)

    def test_ui_has_one_start_date_full_year_default_and_date_changes_do_not_fetch(self):
        from streamlit.testing.v1 import AppTest
        with tempfile.TemporaryDirectory() as folder:
            store = KI.Store(Path(folder) / 'period.sqlite3')
            cache = history('HUMA')
            with store.transaction() as db:
                daily.write_value(db, 'daily_analog:HUMA', cache, NOW)
            code = ('from pathlib import Path\nimport KI, signal_comparison\n' +
                    f'signal_comparison.render(KI.Store(Path({str(store.path)!r})))')
            with patch.object(view, 'datetime', FixedDate), patch.object(daily, 'refresh', return_value='CACHED') as refresh:
                app = AppTest.from_string(code).run(timeout=30)
                refresh.assert_not_called()
                app.text_input(key='daily_analog_input').set_value('HUMA')
                next(b for b in app.button if b.label == 'Pokaż porównanie okresu').click().run(timeout=30)
                self.assertEqual(len(app.exception), 0)
                self.assertEqual(len(app.date_input), 1)
                self.assertEqual(app.date_input(key='signal_period_from').value,
                                 date.fromisoformat(market_rows(cache, NOW)[0]['session']))
                self.assertEqual(len(app.selectbox), 0)
                refresh.assert_called_once()
                app.date_input(key='signal_period_from').set_value(date(2026, 8, 1)).run(timeout=30)
                self.assertEqual(len(app.exception), 0)
                self.assertTrue(any('Wybrany okres: 2026-08-01' in c.value for c in app.caption))
                self.assertTrue(any('Dostępne 52 tygodnie:' in c.value for c in app.caption))
                refresh.assert_called_once()
                next(b for b in app.button if b.label == 'Wyczyść').click().run(timeout=30)
                self.assertEqual(len(app.exception), 0)
                self.assertEqual(app.text_input(key='daily_analog_input').value, '')


if __name__ == '__main__':
    unittest.main()
