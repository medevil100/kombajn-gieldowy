"""Production failure regressions, source binding and real SQLite/UI; no provider calls."""
import copy
import json
import unittest
from unittest.mock import patch

import jsonschema
import KI
import ai_assessment
import final_company_review as review
import test_final_company_review_20261106 as fixture_module


class ValidationProductionTests(unittest.TestCase):
    def company(self, sources=None):
        f=fixture_module.FinalCompanyReviewTests()
        f.setUp();self.addCleanup(f.doCleanups);f.prepare(1)
        ev=KI.load_payload(f.rows('events')[0]['payload'])
        ev['snapshot']['company_name']='Emitent'
        ctx={'sources':sources or [],'cutoff':ev['snapshot']['acquired_at'],
             'issuer_identity':{'ticker':ev['snapshot']['ticker'],'aliases':['Emitent']}}
        ctx['analysis_manifest']=KI.build_analysis_manifest(ev,ctx)
        ctx['ai_preflight']=KI.automatic_ai_preflight(ev,ctx)
        request=KI.event_analysis_request(ev,ctx)
        ctx['prepared_ai_request']=request
        return f,ev,ctx,request

    def sources(self):
        return [{'id':'S1','content':'Emitent announced "a study" with cash of $9.8 million.',
                 'published_at':fixture_module.NOW.isoformat()},
                {'id':'S2','content':'Emitent opublikował raport dotyczący przebiegu badań klinicznych.',
                 'published_at':fixture_module.NOW.isoformat()}]

    def test_quote_text_never_enters_schema_enums_and_decimal_is_not_cut(self):
        f,ev,ctx,request=self.company(self.sources())
        data=json.loads(request['messages'][1]['content'])['source_context']
        self.assertEqual(data['quote_catalog'][0]['fact'],self.sources()[0]['content'])
        item=request['response_format']['json_schema']['schema']['properties']['context']['items']
        self.assertEqual(item['anyOf'][0]['properties']['fact']['enum'],['Q1'])
        self.assertNotIn('a study',json.dumps(request['response_format']))
        self.assertIn('"a study"',data['quote_catalog'][0]['fact'])

    def test_quote_must_belong_to_selected_source_in_schema_and_local_validation(self):
        f,ev,ctx,request=self.company(self.sources())
        value=f.answer();value['context']=[{'source_id':'S2','fact':'Q1'}]
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.validate(value,request['response_format']['json_schema']['schema'])
        clean=KI.validate_event_analysis(value,ev['snapshot'],ctx)
        self.assertEqual(clean['context'],[])
        self.assertTrue(any('innego źródła' in x for x in clean['quality_issues']))

    def test_no_eligible_quotes_requires_empty_context_instead_of_unavailable(self):
        f,ev,ctx,request=self.company([{'id':'S1','content':'Privacy policy and copyright reserved.'}])
        schema=request['response_format']['json_schema']['schema']
        value=f.answer()
        jsonschema.validate(value,schema)
        value['context']=[{'source_id':'S1','fact':'UNAVAILABLE'}]
        with self.assertRaises(jsonschema.ValidationError):jsonschema.validate(value,schema)
        self.assertEqual(schema['properties']['context']['maxItems'],0)

    def test_actual_production_numeric_axes_are_rejected_before_and_after_http(self):
        f,ev,ctx,request=self.company()
        examples={
            'movement':'Cena wzrosła o 15,74% w porównaniu do bazy, co wskazuje na silny trend wzrostowy. Wzrost ten jest wspierany przez zgodność wskaźników technicznych, takich jak SMA, MACD i RSI, które potwierdzają kierunek ruchu.',
            'activity':'Wolumen sesji wyniósł 93843, co jest znacznie powyżej średniej godzinnej wynoszącej 30496.55. Wzrost wolumenu sugeruje zwiększone zainteresowanie inwestorów. Jednakże, brak pełnych danych o wolumenie całej godziny ogranicza pełną ocenę aktywności.'}
        for key,text in examples.items():
            with self.subTest(axis=key):
                value=f.answer();value['assessment'][key]=text
                with self.assertRaises(jsonschema.ValidationError):
                    jsonschema.validate(value,request['response_format']['json_schema']['schema'])
                clean=KI.validate_event_analysis(value,ev['snapshot'],ctx)
                self.assertTrue(KI.analysis_publication_issues(clean,True))
                self.assertTrue(any('niedozwolone cyfry' in x for x in clean['quality_issues']))

    def test_neutral_risk_for_investors_is_allowed_but_behaviour_and_cause_still_rejected(self):
        neutral='Szeroki spread może prowadzić do niekorzystnych warunków wykonania, co zwiększa ryzyko dla inwestorów.'
        self.assertFalse(ai_assessment.unsupported_story(neutral))
        for claim in (
            'Zwiększona aktywność wolumenu może sugerować rosnące zainteresowanie inwestorów w kontekście wyników finansowych.',
            'Cena akcji Clene wzrosła w wyniku pozytywnych informacji o postępach w badaniach klinicznych.',
            'Inwestorzy reagują na wyniki.',
            'Zainteresowanie inwestorów zwiększa ryzyko dla inwestorów.'):
            self.assertTrue(ai_assessment.unsupported_story(claim),claim)

    def test_rsi_valuation_and_invented_cause_remain_blocking(self):
        f,ev,ctx,request=self.company()
        value=f.answer()
        value['technical'][1]['interpretation']='Momentum RSI wskazuje na przewartościowanie, co może sugerować potencjalne osłabienie ruchu.'
        clean=KI.validate_event_analysis(value,ev['snapshot'],ctx)
        self.assertTrue(any('RSI' in x for x in clean['quality_issues']))
        self.assertTrue(KI.analysis_publication_issues(clean,True))

    def test_one_call_pipeline_expands_literal_quote_and_keeps_raw_provider_response(self):
        f,ev,ctx,request=self.company(self.sources())
        raw=f.answer();raw['context']=[{'source_id':'S1','fact':'Q1'}]
        jsonschema.validate(raw,request['response_format']['json_schema']['schema'])
        body={'choices':[{'finish_reason':'stop','message':{'content':json.dumps(raw)}}],
              'model':'offline-fixture','usage':{'total_tokens':1}}
        with f.store.transaction() as db:
            db.execute('UPDATE events SET payload=?',(KI.json_text(ev),))
            db.execute("UPDATE analysis_jobs SET state='PENDING_AI',context=?",(KI.json_text(ctx),))
        with patch.object(KI,'service_http',return_value=body) as http:
            self.assertTrue(KI.process_analysis_once(f.store,{'OPENAI_API_KEY':'fake'}))
            http.assert_called_once()
        row=f.rows('analysis_jobs')[0]
        self.assertEqual(row['state'],'DONE',row['last_error'])
        saved=KI.load_payload(row['result'])
        self.assertEqual(saved['analysis']['context'],[{'source_id':'S1','fact':self.sources()[0]['content']}])
        self.assertEqual(saved['provider']['raw_response'],body)
        self.assertEqual(KI.validate_event_analysis(saved['analysis'],ev['snapshot'],ctx),saved['analysis'])
        self.assertEqual(f.rows('outbox'),[])

    def test_forged_quote_mapping_cannot_override_source_content(self):
        f,ev,ctx,request=self.company(self.sources())
        ctx=copy.deepcopy(ctx)
        payload=json.loads(ctx['prepared_ai_request']['messages'][1]['content'])
        payload['source_context']['quote_catalog'][0]['fact']='Emitent otrzymał finansowanie, którego nie potwierdzają źródła.'
        ctx['prepared_ai_request']['messages'][1]['content']=json.dumps(payload)
        raw=f.answer();raw['context']=[{'source_id':'S1','fact':'Q1'}]
        clean=KI.validate_event_analysis(raw,ev['snapshot'],ctx)
        self.assertEqual(clean['context'],[])
        self.assertTrue(KI.analysis_publication_issues(clean,True))

    def test_legacy_literal_quote_does_not_require_new_mapping(self):
        f,ev,ctx,request=self.company(self.sources())
        ctx.pop('prepared_ai_request')
        raw=f.answer();raw['context']=[{'source_id':'S1','fact':self.sources()[0]['content']}]
        clean=KI.validate_event_analysis(raw,ev['snapshot'],ctx)
        self.assertEqual(clean['context'],raw['context'])
        self.assertFalse(KI.analysis_publication_issues(clean,True))

    def test_failed_review_panel_shows_real_diagnostics_without_api_or_writes(self):
        from streamlit.testing.v1 import AppTest
        f,ev,ctx,request=self.company()
        with f.store.transaction() as db:
            db.execute("UPDATE analysis_jobs SET state='FAILED',last_error=?,result=NULL",('OpenAI HTTP 400: fixture sk-not-a-real-secret-value',))
        with f.store.connection() as db:before=list(db.iterdump())
        script='import KI\nfrom pathlib import Path\nKI.company_review.render(KI,KI.Store(Path('+repr(str(f.store.path))+')))'
        with patch.object(KI,'service_http',side_effect=AssertionError('No UI API calls')):
            app=AppTest.from_string(script).run(timeout=30)
        self.assertFalse(app.exception,list(app.exception))
        warnings=' '.join(x.value for x in app.warning)
        self.assertIn('HTTP 400',warnings)
        self.assertNotIn('sk-not-a-real-secret-value',warnings)
        with f.store.connection() as db:self.assertEqual(list(db.iterdump()),before)


if __name__=='__main__':unittest.main()
