"""Rzeczywisty renderer Streamlit dla zapisanych statusów; bez usług sieciowych."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from streamlit.testing.v1 import AppTest
import KI
from test_tavily_search_contract import snap,source


class TavilyPanelTests(unittest.TestCase):
    def render(self,research):
        turn={'id':'local-panel-test','state':'DONE','context':json.dumps({'research':research}), 'metadata':None}
        script='import KI\nKI.render_manual_service_status('+repr(turn)+')\n'
        app=AppTest.from_string(script).run(timeout=30)
        self.assertEqual(len(app.exception),0)
        return app

    def test_current_undated_result_has_diagnostic_link_and_explicit_status(self):
        research=KI.normalize_tavily_context({'results':[source(None)]},snap(website='https://stalexport-autostrady.pl'))
        research.update(status='DONE',research_version=4,issuer_domain='stalexport-autostrady.pl')
        app=self.render(research)
        self.assertTrue(any('daty lub czasu' in x.value for x in app.info))
        self.assertTrue(any('poza źródłami GPT' in x.value for x in app.caption))
        self.assertEqual(len(app.get('link_button')),1)
        self.assertIn('stalexport-autostrady.pl',str(app.get('link_button')[0].proto))

    def test_legacy_empty_record_remains_readable(self):
        research={'status':'DONE','sources':[],'received_results':0,'issuer_filter_version':1,
                  'attempts':[{'scope':'fresh','status':'DONE','request':{
                      'query':'stare zapytanie','start_date':'2026-10-01','end_date':'2026-10-09',
                      'include_domains':['gpw.pl'],'filter_by_published_date':True},'received_results':0,'accepted':0}]}
        app=self.render(research)
        self.assertTrue(any('pustą listę' in x.value for x in app.info))
        self.assertTrue(any('mogły zostać pominięte' in x.value for x in app.caption))

    def test_service_monitor_reads_legacy_and_current_search_contexts(self):
        stamp = '2026-11-04T14:00:00+00:00'
        with TemporaryDirectory() as folder:
            db = Path(folder) / 'monitor.sqlite3'
            store = KI.Store(db)
            contexts = [
                ('legacy', {'sources': []}),
                ('current', {'sources': [], 'excluded': 0, 'cutoff': stamp}),
            ]
            with store.transaction() as connection:
                for event_id, context in contexts:
                    evidence = {
                        'snapshot': {'ticker': 'NVG.WA', 'interval': '1h',
                                     'candle_time': stamp, 'candle_status': 'CLOSED',
                                     'acquired_at': stamp, 'price': 1.0},
                        'reference': {'price': 0.9}, 'reasons': [],
                        'thresholds': {'price_threshold_pct': 1.0},
                    }
                    connection.execute('INSERT INTO events VALUES(?,?,?,?,?)',
                                       (event_id, 'NVG.WA', '1h', stamp, json.dumps(evidence)))
                    connection.execute(
                        'INSERT INTO analysis_jobs(event_id,state,context,updated_at) VALUES(?,?,?,?)',
                        (event_id, 'PENDING_AI', json.dumps(context), stamp),
                    )
            script = 'from pathlib import Path\nimport KI\nKI.render_service_panel(KI.Store(Path(' + repr(str(db)) + ')))'
            app = AppTest.from_string(script).run(timeout=30)
            self.assertEqual(len(app.exception), 0)
            captions = [element.value for element in app.caption]
            self.assertIn('Przyjęto źródeł: 0 · odrzucono: brak w zapisie · granica czasu: brak w zapisie', captions)
            self.assertIn('Przyjęto źródeł: 0 · odrzucono: 0 · granica czasu: ' + stamp, captions)


if __name__=='__main__':unittest.main(verbosity=2)
