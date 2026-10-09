"""Rzeczywisty renderer Streamlit dla zapisanych statusów; bez usług sieciowych."""
import json
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


if __name__=='__main__':unittest.main(verbosity=2)
