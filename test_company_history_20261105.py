import json
import sqlite3
import tempfile
import unittest
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import KI
import company_history as history


NOW = datetime(2026, 11, 5, 18, tzinfo=timezone.utc)
AT = '2026-11-05T12:00:00+00:00'


class ReadOnly:
    def __init__(self, path):
        self.path = path

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path.as_uri() + '?mode=ro', uri=True, isolation_level=None)
        db.row_factory = sqlite3.Row
        try:
            yield db
        finally:
            db.close()


class CompanyHistoryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name) / 'history.sqlite3'
        self.writer = KI.Store(self.path)
        self.store = ReadOnly(self.path)

    def observation(self, at=AT, ticker='OLD', payload=None):
        with self.writer.connection() as db:
            db.execute('INSERT INTO observations(ticker,interval,candle_time,acquired_at,candle_status,payload) VALUES(?,?,?,?,?,?)',
                       (ticker, '1h', AT, at, 'CLOSED', payload or json.dumps({'price': 2., 'currency': 'USD', 'volume': 100})))

    def pipeline(self):
        with self.writer.connection() as db:
            db.execute("INSERT INTO events VALUES('event','OLD','1h',?,'{}')", (AT,))
            db.execute("INSERT INTO signal_confirmations VALUES(?,'OLD',2,5,'USD')", (AT,))
            db.execute("INSERT INTO opportunities VALUES('seq','OLD',?,?,'SELECTED','cycle','{}',?,?)", (AT, AT, AT, AT))
            db.execute("INSERT INTO alert_decisions(seq,ts,stage,should_alert,reason) VALUES('seq',?,'PREFLIGHT',0,'Brak danych bid/ask')", (AT,))
            context = json.dumps({'sources': [{'title': 'Raport'}], 'excluded': 2})
            result = json.dumps({'analysis': {'assessment': 'Zapisany wniosek', 'risks': ['Ryzyko płynności']}})
            db.execute("INSERT INTO analysis_jobs(event_id,state,context,result,updated_at) VALUES('event','DONE',?,?,?)", (context, result, AT))
            db.execute("INSERT INTO research_requests(event_id,state,query,cutoff,raw_response,created_at,updated_at) VALUES('event','COMPLETED','Nazwa spółki','2026-10-01',?,?,?)",
                       (json.dumps({'results': [{}, {}, {}]}), AT, AT))
            db.execute("INSERT INTO outbox(id,event_id,kind,message,status,created_at) VALUES('message','event','ANALYSIS','Zachowana wiadomość','DELIVERED',?)", (AT,))
            db.execute("INSERT INTO analysis_rejections VALUES('rejection','event','Niepełny materiał','{}',?)", (AT,))
            db.execute("INSERT INTO gpt_chat_turns(id,question,context,answer,state,created_at,finished_at) VALUES('chat','Moje pytanie',?,'Odpowiedź','DONE',?,?)",
                       (json.dumps({'ticker': 'OLD'}), AT, AT))
            report = json.dumps({'rating': 'Obserwacja', 'reports': {'Fundamenty': 'Zachowany raport'}})
            db.execute("INSERT INTO deep_reports VALUES('deep','OLD','DONE',?,NULL,?,?)", (report, AT, AT))
            db.execute("INSERT INTO daily_candles VALUES('OLD','2026-11-04',2,3,1,2.5,100,?,'Yahoo','{}')", (AT,))

    def test_archived_ticker_and_all_pipeline_records_are_available_read_only(self):
        self.observation()
        self.pipeline()
        self.assertIn('OLD', history.tickers(self.store))
        with self.writer.connection() as db:
            before = list(db.iterdump())
        result = history.page(self.store, 'OLD', at=NOW)
        self.assertEqual({r['source'] for r in result['rows']},
                         {'observation', 'daily', 'signal', 'opportunity', 'decision', 'research', 'analysis', 'telegram', 'manual', 'deep', 'rejection'})
        analysis = next(r for r in result['rows'] if r['source'] == 'analysis')
        self.assertEqual(analysis['summary'], 'Zapisany wniosek')
        self.assertIn(('Ryzyka', 'Ryzyko płynności'), analysis['fields'])
        research = next(r for r in result['rows'] if r['source'] == 'research')
        self.assertIn(('Źródła przyjęte w KI', 1), research['fields'])
        deep = next(r for r in result['rows'] if r['source'] == 'deep')
        self.assertIn(('Fundamenty', 'Zachowany raport'), deep['fields'])
        with self.writer.connection() as db:
            self.assertEqual(before, list(db.iterdump()))

    def test_delivery_requires_saved_api_receipt_and_keeps_actual_delivery_time(self):
        self.pipeline()
        first = history.page(self.store, 'OLD', ['Telegram'], at=NOW)['rows'][0]
        self.assertNotIn('potwierdzono wysyłkę', first['title'])
        delivered = '2026-11-05T14:05:00+01:00'
        with self.writer.connection() as db:
            db.execute("INSERT INTO delivery_receipts VALUES('message','private-chat',25,?)", (delivered,))
        row = history.page(self.store, 'OLD', ['Telegram'], at=NOW)['rows'][0]
        self.assertEqual(row['at'], delivered)
        self.assertIn('potwierdzono wysyłkę', row['title'])
        self.assertNotIn('private-chat', str(row))

    def test_pagination_filters_and_timezone_sorting(self):
        for i in range(45):
            self.observation((NOW - timedelta(minutes=i)).isoformat())
        self.observation((NOW + timedelta(minutes=1)).isoformat())
        self.observation((NOW - timedelta(days=31)).isoformat())
        first = history.page(self.store, 'OLD', ['Rynek'], at=NOW)
        second = history.page(self.store, 'OLD', ['Rynek'], index=2, at=NOW)
        third = history.page(self.store, 'OLD', ['Rynek'], index=99, at=NOW)
        self.assertEqual((first['count'], first['pages'], len(third['rows'])), (45, 3, 5))
        self.assertFalse({r['id'] for r in first['rows']} & {r['id'] for r in second['rows']})
        self.assertEqual(history.page(self.store, 'OLD', [], at=NOW)['count'], 0)
        self.assertEqual(history.page(self.store, 'OLD', ['Rynek'], days=None, at=NOW)['count'], 46)
        self.observation('2026-11-05T18:30:00+01:00')  # 17:30 UTC
        row = history.page(self.store, 'OLD', ['Rynek'], index=2, at=NOW)['rows']
        self.assertIn('2026-11-05T18:30:00+01:00', [r['at'] for r in row])
        moments = [datetime.fromisoformat(r['at']) for r in row]
        self.assertEqual(moments, sorted(moments, reverse=True))

    def test_malformed_legacy_json_does_not_hide_other_history(self):
        self.pipeline()
        self.observation(payload='{bad')
        with self.writer.connection() as db:
            db.execute("UPDATE analysis_jobs SET result='[]',context='{bad'")
            db.execute("UPDATE research_requests SET raw_response='{bad'")
            db.execute("INSERT INTO gpt_chat_turns(id,question,context,state,created_at) VALUES('bad','bad','{bad','FAILED',?)", (AT,))
        self.assertIn('OLD', history.tickers(self.store))
        self.assertEqual(history.page(self.store, 'OLD', at=NOW)['count'], 11)

    def test_local_review_is_labeled_without_fabricated_ai_output(self):
        self.pipeline()
        result = {'local_only': True, 'provider': {'not_called': True}, 'local_review': {'label': 'Wskazania mieszane'},
                  'ai_preflight': {'skip_reasons': ['Brak pytania wymagającego AI']}}
        with self.writer.connection() as db:
            db.execute('UPDATE analysis_jobs SET result=?', (json.dumps(result),))
        row = history.page(self.store, 'OLD', ['Analizy AI'], at=NOW)['rows']
        local = next(r for r in row if r['source'] == 'analysis')
        self.assertEqual(local['title'], 'Ocena lokalna')
        self.assertEqual(local['summary'], 'Wskazania mieszane')
        self.assertIn(('Powody pominięcia AI', 'Brak pytania wymagającego AI'), local['fields'])

    def test_cards_escape_content_and_hide_provider_tokens(self):
        self.observation()
        rows = history.page(self.store, 'OLD', at=NOW)['rows']
        rows[0]['summary'] = '<script>test</script> sk-proj-' + 'x' * 50
        rows[0]['fields'].append(('Błąd', 'https://api.telegram.org/bot123456789:' + 'A' * 35 + '/sendMessage'))
        html = history.cards_html(rows)
        self.assertNotIn('<script>', html)
        self.assertIn('&lt;script&gt;', html)
        self.assertNotIn('x' * 50, html)
        self.assertNotIn('A' * 35, html)
        self.assertIn('min-height:44px', html)
        self.assertIn('@media(max-width:600px)', html)

    def test_mobile_view_filters_and_page_navigation_do_not_call_providers(self):
        from streamlit.testing.v1 import AppTest
        for i in range(25):
            self.observation((datetime.now(timezone.utc) - timedelta(minutes=i + 1)).isoformat())
        code = 'from pathlib import Path\nimport KI, company_history\n' + f'company_history.render_ki_log(KI.Store(Path({str(self.path)!r})))'
        with patch.object(KI, 'fetch_market', side_effect=AssertionError('unexpected market request')):
            app = AppTest.from_string(code).run(timeout=30)
            self.assertEqual(len(app.exception), 0)
            self.assertEqual(app.text_input(key='company_history_symbol').value, '')
            app.text_input(key='company_history_symbol').set_value('OLD')
            next(b for b in app.button if b.label == 'Pokaż historię').click().run(timeout=30)
            app.number_input(key='company_history_page').set_value(2).run(timeout=30)
            self.assertEqual(len(app.exception), 0)
            self.assertTrue(any('strona 2 z 2' in c.value for c in app.caption))
            app.multiselect(key='company_history_categories').set_value(['Telegram']).run(timeout=30)
            self.assertEqual(len(app.exception), 0)
            self.assertTrue(any('Brak zapisów' in c.value for c in app.info))

    def test_history_is_accessible_from_main_menu_without_current_observations(self):
        from streamlit.testing.v1 import AppTest
        self.pipeline()
        script = 'from pathlib import Path\nimport KI\n' + f'KI.run_streamlit(Path({str(self.path)!r}))'
        app = AppTest.from_string(script).run(timeout=30)
        app.radio(key='panel_view').set_value('Historia spółki').run(timeout=30)
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(app.text_input(key='market_history_input').value, '')
        self.assertTrue(any('Yahoo · 52 tygodnie' in item.value for item in app.subheader))

    def test_empty_search_does_not_load_history_and_ticker_can_be_changed_and_cleared(self):
        from streamlit.testing.v1 import AppTest
        now = datetime.now(timezone.utc).isoformat()
        for i in range(25):
            self.observation(now)
        self.observation(now, ticker='OTHER')
        code = 'from pathlib import Path\nimport KI, company_history\n' + f'company_history.render_ki_log(KI.Store(Path({str(self.path)!r})))'
        with patch.object(history, 'page', side_effect=AssertionError('History must remain unloaded')):
            app = AppTest.from_string(code).run(timeout=30)
            self.assertEqual(len(app.exception), 0)
        self.assertEqual(app.text_input(key='company_history_symbol').value, '')
        app.text_input(key='company_history_symbol').set_value(' old ')
        next(b for b in app.button if b.label == 'Pokaż historię').click().run(timeout=30)
        app.number_input(key='company_history_page').set_value(2).run(timeout=30)
        app.text_input(key='company_history_symbol').set_value('OTHER')
        next(b for b in app.button if b.label == 'Pokaż historię').click().run(timeout=30)
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(app.number_input(key='company_history_page').value, 1)
        self.assertTrue(any('OTHER · 1 zapisów' in c.value for c in app.caption))
        next(b for b in app.button if b.label == 'Wyczyść').click().run(timeout=30)
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(app.text_input(key='company_history_symbol').value, '')
        self.assertFalse(any(c.key == 'company_history_page' for c in app.number_input))


    def test_daily_colors_compare_stored_close_not_candle_body(self):
        with self.writer.connection() as db:
            for day, opening, close in [('2026-11-01', 10, 10), ('2026-11-02', 13, 12),
                                        ('2026-11-03', 9, 11), ('2026-11-04', 12, 11)]:
                db.execute("INSERT INTO daily_candles VALUES('OLD',?,?,14,8,?,100,?,'Yahoo','{}')",
                           (day, opening, close, day + 'T17:00:00+00:00'))
        rows = history.page(self.store, 'OLD', ['Rynek'], at=NOW)['rows']
        by_day = {row['id']: row for row in rows}
        self.assertEqual([by_day['2026-11-0'+str(i)]['daily_movement'] for i in range(1,5)],
                         ['unknown', 'up', 'down', 'flat'])
        html = history.cards_html(rows)
        for direction in ('up', 'down', 'flat', 'unknown'):
            self.assertIn('class="ki-history-card daily-' + direction + '"', html)
        self.assertIn('Poprzednia zapisana sesja', html)
        for value in (None, 'NaN', float('inf'), 0, -1):
            self.assertEqual(history.daily_movement(10, value)['direction'], 'unknown')

    def test_more_than_nineteen_pages_and_explicit_refresh_loads_new_records(self):
        from streamlit.testing.v1 import AppTest
        now = datetime.now(timezone.utc) - timedelta(minutes=2)
        with self.writer.connection() as db:
            db.executemany('INSERT INTO observations(ticker,interval,candle_time,acquired_at,candle_status,payload) '
                           'VALUES(?,?,?,?,?,?)', [('OLD', '1h', AT,
                           (now - timedelta(seconds=i)).isoformat(), 'CLOSED', '{}') for i in range(401)])
        result = history.page(self.store, 'OLD', at=datetime.now(timezone.utc))
        self.assertEqual((result['count'], result['pages']), (401, 21))
        code = 'from pathlib import Path\nimport KI, company_history\n' + f'company_history.render_ki_log(KI.Store(Path({str(self.path)!r})))'
        app = AppTest.from_string(code).run(timeout=30)
        app.text_input(key='company_history_symbol').set_value('OLD')
        next(b for b in app.button if b.label == 'Pokaż historię').click().run(timeout=30)
        self.assertEqual(app.selectbox(key='company_history_range').value, 'Cała zapisana historia')
        app.number_input(key='company_history_page').set_value(21).run(timeout=30)
        anchor = app.session_state['company_history_at']
        self.observation(datetime.now(timezone.utc).isoformat())
        app.run(timeout=30)
        self.assertEqual(app.session_state['company_history_at'], anchor)
        self.assertTrue(any('401 zapisów' in c.value for c in app.caption))
        app.button(key='company_history_refresh').click().run(timeout=30)
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(app.number_input(key='company_history_page').value, 1)
        self.assertTrue(any('402 zapisów' in c.value for c in app.caption))
        self.observation(datetime.now(timezone.utc).isoformat())
        app.run(timeout=30)
        self.assertTrue(any('403 zapisów' in c.value for c in app.caption))


if __name__ == '__main__':
    unittest.main()
