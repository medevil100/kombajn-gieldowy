"""Replay the recorded FBIO failure; constrained generation, no live providers."""
import copy
import json
import re
import shutil
import subprocess
import unittest
from unittest.mock import patch

import jsonschema
import KI
import ai_assessment
import prompt_policy
import test_validation_20261109 as validation_fixture

# Literal production response is inserted below; never a corrected replacement.
RECORDED_FBIO = {'assessment': {'movement': 'Cena wzrosła o  łącznie  łącznie  łącznie  łącznie  łącznie  łącznie  łącznie  łącznie  łącznie  łącznie  łącznie  łącznie  łącznie  łącznie  łącznie  łącznie  łącznie  łącznie  łącznie  łącznie  łącznie  łącznie  łącznie  łącznie  łącznie  łącznie  łącznie  łącznie  łącznie  łącznie  łącznie  łącznie  łącznie  łącznie  łącznie  łącznie  łącznie  łącznie  łącznie  łącznie  łącznie  łącznie  łącznie  łącznie  łącznie  łącznie  łącznie  łącznie  łącznie  łącznie  łącznie  łącznie  łącznie  łącznie  łącznie  łącznie  łącznie  łącznie  łącznie  łącznie  łącznie  łącznie  łącznie  łącznie  łącznie ', 'activity': 'Wolumen w bieżącej świecy wynosi  łącznie  łącznie  łącznie  łącznie  łącznie  łącznie  łącznie  łącznie  łącznie  łącznie  łącznie  łącznie  łącznie  łącznie  łącznie  łącznie  łącznie  łącznie  łącznie  łącznie  łącznie  łącznie  łącznie  łącznie  łącznie  łącznie  łącznie  łącznie  łącznie  łącznie  łącznie  łącznie  łącznie  łącznie  łącznie  łącznie  łącznie  łącznie  łącznie  łącznie  łącznie  łącznie  łącznie  łącznie  łącznie  łącznie  łącznie  łącznie  łącznie  łącznie  łącznie  łącznie  łącznie  łącznie  łącznie  łącznie  łącznie  łącznie  łącznie  łącznie  łącznie  łącznie  łącznie ', 'risk': 'Ryzyko związane z brakiem potwierdzonego czasu aktualizacji bid/ask może wpłynąć na realizację transakcji. Dodatkowo, niska świeżość ofert bid/ask może prowadzić do niepewności w realizacji zleceń.'}, 'hypotheses': ['Wzrost ceny może być spowodowany pozytywnymi informacjami o wynikach finansowych emitenta.', 'Zwiększona aktywność handlowa może być wynikiem spekulacji inwestorów przed ogłoszeniem wyników.']}


class FbioContractTests(unittest.TestCase):
    def company(self):
        fixture=validation_fixture.ValidationProductionTests();self.addCleanup(fixture.doCleanups)
        return fixture.company()

    def short_answer(self,f):
        value=f.answer()
        value['assessment']={
            'movement':'Przebieg sesji potwierdza kierunek wzrostu. Cena jest powyżej szybkiej średniej.',
            'activity':'Wolumen jest powyżej średniej. Bieżący pomiar jest częściowy.',
            'risk':'Brak ofert ogranicza ocenę ryzyka. Nie ustalono warunków wykonania.'}
        return value

    def test_exact_recorded_fbio_loop_is_rejected_without_mutation(self):
        f,ev,ctx,request=self.company()
        value=f.answer();value['assessment']=copy.deepcopy(RECORDED_FBIO['assessment'])
        value['hypotheses']=copy.deepcopy(RECORDED_FBIO['hypotheses'])
        before=copy.deepcopy(value)
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.validate(value,request['response_format']['json_schema']['schema'])
        clean=KI.validate_event_analysis(value,ev['snapshot'],ctx)
        self.assertTrue(any('zapętlony' in x for x in clean['quality_issues']))
        self.assertTrue(any('puste hypotheses' in x for x in clean['quality_issues']))
        self.assertTrue(KI.analysis_publication_issues(clean,True))
        self.assertEqual(value,before)

    def test_schema_requires_two_to_four_completed_sentences_not_padding(self):
        f,ev,ctx,request=self.company()
        schema=request['response_format']['json_schema']['schema']
        axes=schema['properties']['assessment']['properties']
        for field in axes.values():self.assertNotIn('minLength',field)
        good=self.short_answer(f)
        jsonschema.validate(good,schema)
        self.assertFalse(KI.analysis_publication_issues(KI.validate_event_analysis(good,ev['snapshot'],ctx),True))
        for text in ('Cena wzrosła o '+' łącznie '*60,
                     'Przebieg sesji jest wzrostowy.',
                     'Przebieg sesji jest wzrostowy. Cena jest wyżej',
                     'Wzrost. Kierunek. Sesja. Cena. Momentum.'):
            bad=copy.deepcopy(good);bad['assessment']['movement']=text
            with self.assertRaises(jsonschema.ValidationError):jsonschema.validate(bad,schema)

    def test_final_hypotheses_are_empty_but_verified_source_context_is_retained(self):
        f,ev,ctx,request=self.company()
        self.assertEqual(ctx['analysis_manifest']['hypotheses_policy'],'EMPTY')
        self.assertEqual(request['response_format']['json_schema']['schema']['properties']['hypotheses']['maxItems'],0)
        good=self.short_answer(f)
        good['hypotheses']=['Raport może stanowić historyczne tło spółki.']
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.validate(good,request['response_format']['json_schema']['schema'])
        clean=KI.validate_event_analysis(good,ev['snapshot'],ctx)
        self.assertEqual(clean['hypotheses'],[])
        self.assertTrue(KI.analysis_publication_issues(clean,True))

    def test_completed_loop_or_duplicate_sentences_are_still_blocked_locally(self):
        f,ev,ctx,request=self.company()
        for text in ('Przebieg sesji pokazuje '+'łącznie '*6+'. Cena jest powyżej średniej.',
                     'Przebieg sesji jest wzrostowy. Przebieg sesji jest wzrostowy.',
                     'Przebieg sesji pokazuje wzrost. '+'Cena jest powyżej średniej '*4+'.'):
            value=self.short_answer(f);value['assessment']['movement']=text
            clean=KI.validate_event_analysis(value,ev['snapshot'],ctx)
            self.assertTrue(KI.analysis_publication_issues(clean,True),text)

    def test_single_mocked_call_saves_valid_review_and_unmodified_raw_response(self):
        f,ev,ctx,request=self.company();raw=self.short_answer(f)
        body={'choices':[{'finish_reason':'stop','message':{'content':json.dumps(raw)}}],
              'model':'offline-fbio-regression','usage':{'total_tokens':1}}
        with f.store.transaction() as db:
            db.execute('UPDATE events SET payload=?',(KI.json_text(ev),))
            db.execute("UPDATE analysis_jobs SET state='PENDING_AI',context=?",(KI.json_text(ctx),))
        with patch.object(KI,'service_http',return_value=body) as http:
            self.assertTrue(KI.process_analysis_once(f.store,{'OPENAI_API_KEY':'fake'}))
            http.assert_called_once()
        row=f.rows('analysis_jobs')[0]
        self.assertEqual(row['state'],'DONE',row['last_error'])
        saved=KI.load_payload(row['result'])
        self.assertEqual(saved['provider']['raw_response'],body)
        self.assertEqual(saved['analysis']['assessment'],raw['assessment'])
        self.assertEqual(f.rows('outbox'),[])

    def test_old_manifest_retains_old_checks_and_old_record_is_unchanged(self):
        f,ev,ctx,request=self.company();manifest=copy.deepcopy(ctx['analysis_manifest'])
        manifest.pop('assessment_contract');manifest.pop('hypotheses_policy')
        axes=self.short_answer(f)['assessment'];before=copy.deepcopy(RECORDED_FBIO)
        _,errors=ai_assessment.validate_axes(axes,ev['snapshot'],manifest)
        self.assertTrue(any('pełniejszego uzasadnienia' in x for x in errors))
        self.assertEqual(RECORDED_FBIO,before)

    def test_new_form_does_not_allow_cause_numbers_or_unsafe_liquidity_claims(self):
        f,ev,ctx,request=self.company()
        for field,text in (
            ('movement','Przebieg sesji jest wzrostowy w wyniku dobrych wyników finansowych. Cena jest powyżej średniej.'),
            ('activity','Wolumen wyniósł ٢ tysiące. Pomiar jest częściowy.'),
            ('risk','Ryzyko jest niskie dzięki wysokiej płynności. Oferty nie mają potwierdzonego czasu.')):
            value=self.short_answer(f);value['assessment'][field]=text
            clean=KI.validate_event_analysis(value,ev['snapshot'],ctx)
            self.assertTrue(KI.analysis_publication_issues(clean,True),text)

    def test_javascript_sentence_pattern_matches_python_for_real_failure_and_valid_prose(self):
        node=shutil.which('node')
        if not node:self.skipTest('Node.js unavailable; provider regex verified on Windows.')
        f,ev,ctx,request=self.company()
        pattern=request['response_format']['json_schema']['schema']['properties']['assessment']['properties']['movement']['pattern']
        values=list(RECORDED_FBIO['assessment'].values())+list(self.short_answer(f)['assessment'].values())
        values+=['Przebieg sesji wzrósł o ٢%. Cena jest wyżej.']
        payload={'pattern':pattern,'values':values,'expected':[bool(re.fullmatch(pattern,t)) for t in values]}
        script="const x=JSON.parse(require('fs').readFileSync(0,'utf8')); for(const flags of ['', 'u']) { const r=new RegExp(x.pattern,flags); x.values.forEach((v,i)=>{if(r.test(v)!==x.expected[i])throw Error('Regex engines disagree');});}"
        result=subprocess.run([node,'-e',script],input=json.dumps(payload),text=True,encoding='utf-8',
                              capture_output=True,timeout=20)
        self.assertEqual(result.returncode,0,result.stderr)


if __name__=='__main__':unittest.main()
