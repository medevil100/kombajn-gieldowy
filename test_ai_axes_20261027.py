import copy
import json
import unittest
import tempfile
from pathlib import Path
import KI
from ai_assessment import unsupported_story,summary_text
import test_alert_quality_20261026 as fixtures


class AssessmentAxesTests(unittest.TestCase):
    def sample(self):
        ev,result=fixtures.AlertQualityTests().sample()
        ctx={'sources':[],'analysis_manifest':KI.build_analysis_manifest(ev,{'sources':[]})}
        result['assessment']={'movement':'Potwierdzony spadek ma mieszane wskazania.',
                              'activity':'Wolumen trwającej świecy nie rozstrzyga aktywności całej godziny.',
                              'risk':'Brak ofert ogranicza ocenę ryzyka wykonania.'}
        return ev,result,ctx

    def test_schema_requires_each_axis_with_no_extra_fields(self):
        ev,result,ctx=self.sample();s=KI.analysis_schema(ev['snapshot'],ctx)['properties']['assessment']
        self.assertEqual(s['type'],'object');self.assertEqual(set(s['required']),{'movement','activity','risk'})
        self.assertFalse(s['additionalProperties'])

    def test_valid_three_axes_are_composed_without_filling_missing_data(self):
        ev,result,ctx=self.sample();before=copy.deepcopy(result)
        clean=KI.validate_event_analysis(result,ev['snapshot'],ctx)
        self.assertFalse(KI.analysis_publication_issues(clean,True))
        self.assertEqual(summary_text(clean),' '.join(result['assessment'].values()))
        self.assertEqual(result,before)
        self.assertIn('Wniosek AI: '+summary_text(clean),KI.opportunity_message('e',ev,ctx,clean))
        self.assertEqual(KI.validate_event_analysis(clean,ev['snapshot'],ctx),clean)

    def test_empty_or_wrong_axis_blocks_publication_and_remains_stable(self):
        ev,result,ctx=self.sample()
        for value in ('','Dane są ograniczone.'):
            result['assessment']['activity']=value
            clean=KI.validate_event_analysis(result,ev['snapshot'],ctx)
            self.assertTrue(KI.analysis_publication_issues(clean,True))
            self.assertEqual(summary_text(clean),'')
            again=KI.validate_event_analysis(clean,ev['snapshot'],ctx)
            self.assertEqual(again,clean)

    def test_legacy_string_contract_is_retained_only_for_legacy_manifest(self):
        ev,result,ctx=self.sample();result['assessment']=summary_text(result)
        self.assertTrue(KI.analysis_publication_issues(KI.validate_event_analysis(result,ev['snapshot'],ctx),True))
        ctx['analysis_manifest']['version']=2
        self.assertFalse(KI.analysis_publication_issues(KI.validate_event_analysis(result,ev['snapshot'],ctx),True))

    def test_behaviour_narratives_are_rejected_even_when_cautiously_worded(self):
        for value in ('Wzrost może być wynikiem zmiany sentymentu inwestorów.',
                      'Spadek sugeruje realizację zysków.', 'Widać napływ kapitału.', 'Inwestorzy reagują na wyniki.'):
            self.assertTrue(unsupported_story(value),value)
        self.assertFalse(unsupported_story('Brak dowodów na zmianę sentymentu inwestorów.'))
        self.assertTrue(unsupported_story('Wzrost wynika z publikacji wyników.'))
        self.assertFalse(unsupported_story('Publikacja nie dowodzi, że spowodowała wzrost.'))
        ev,result,ctx=self.sample();result['assessment']['movement']='Wzrost może być wynikiem zmiany sentymentu inwestorów.'
        clean=KI.validate_event_analysis(result,ev['snapshot'],ctx)
        self.assertTrue(KI.analysis_publication_issues(clean,True))

    def test_stories_in_technical_and_hypotheses_are_not_published(self):
        ev,result,ctx=self.sample();result['hypotheses']=['Wzrost wynika z realizacji zysków.']
        clean=KI.validate_event_analysis(result,ev['snapshot'],ctx)
        self.assertEqual(clean['hypotheses'],[])
        result['technical'][0]['interpretation']='Wzrost wynika ze zmiany sentymentu.'
        clean=KI.validate_event_analysis(result,ev['snapshot'],ctx)
        self.assertLess(len(clean['technical']),len(result['technical']))

    def test_raw_response_survives_rejected_assessment_without_paid_retry(self):
        ev,result,ctx=self.sample();result['assessment']['activity']='Nie wiem.'
        body={'model':'test','choices':[{'finish_reason':'stop','message':{'content':json.dumps(result)}}]}
        clean,metadata=KI.parse_event_analysis_response(body,ev['snapshot'],ctx)
        self.assertTrue(KI.analysis_publication_issues(clean,True))
        self.assertEqual(metadata['raw_response'],body)

    def test_partial_activity_cannot_be_called_below_average_without_caveat(self):
        ev,result,ctx=self.sample();ev['snapshot']['rvol']=None
        ctx['analysis_manifest']['activity']['status']='PARTIAL'
        result['assessment']['activity']='Wolumen poniżej średniej, co może sugerować ograniczoną aktywność rynku.'
        clean=KI.validate_event_analysis(result,ev['snapshot'],ctx)
        self.assertTrue(KI.analysis_publication_issues(clean,True))

    def test_source_quote_enum_contains_only_literal_source_fragments(self):
        ev,result,ctx=self.sample()
        source={'id':'S1','content':'Emitent opublikował dzisiaj raport o wynikach finansowych. Privacy policy and copyright reserved here.'}
        ctx['sources']=[source]
        fact=KI.analysis_schema(ev['snapshot'],ctx)['properties']['context']['items']['properties']['fact']
        self.assertEqual(fact['enum'],['Emitent opublikował dzisiaj raport o wynikach finansowych.'])

    def test_finish_persists_structured_result_and_does_not_queue_rejected_output(self):
        with tempfile.TemporaryDirectory() as folder:
            store=KI.Store(Path(folder)/'test.sqlite3')
            for event_id,valid in (('good',True),('bad',False)):
                ev,result,ctx=self.sample()
                if not valid:result['assessment']['activity']=''
                with store.transaction() as c:
                    c.execute('INSERT INTO events VALUES(?,?,?,?,?)',(event_id,ev['snapshot']['ticker'],'1h',KI.utc_now(),KI.json_text(ev)))
                    c.execute('INSERT INTO analysis_jobs(event_id,state,context,updated_at) VALUES(?,?,?,?)',
                              (event_id,'BUSY_AI',KI.json_text(ctx),KI.utc_now()))
                KI.finish_analysis(store,event_id,result,{'raw_response':{'test':'preserved'}})
                with store.connection() as c:
                    row=c.execute('SELECT state,result FROM analysis_jobs WHERE event_id=?',(event_id,)).fetchone()
                    self.assertEqual(row['state'],'DONE' if valid else 'REVIEW_REQUIRED')
                    saved=json.loads(row['result'])
                    self.assertIsInstance(saved['analysis']['assessment'],dict)
                    self.assertEqual(saved['provider']['raw_response'],{'test':'preserved'})
                    count=c.execute('SELECT count(*) FROM outbox WHERE event_id=?',(event_id,)).fetchone()[0]
                    self.assertEqual(count,1 if valid else 0)


if __name__=='__main__':unittest.main()
