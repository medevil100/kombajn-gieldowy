"""Grounded final verdicts: real data packages, strict ID schema, raw provider retained."""
import copy
import json
import unittest
from unittest.mock import patch

import jsonschema
import KI
import evidence_review as grounded
import test_final_company_review_20261106 as fixtures
import test_session_context_20261106 as shortened


class EvidenceReviewTests(unittest.TestCase):
    def sample(self,snapshot=None,sources=None):
        f=fixtures.FinalCompanyReviewTests();f.setUp();self.addCleanup(f.doCleanups);f.prepare(1)
        ev=KI.load_payload(f.rows('events')[0]['payload'])
        if snapshot:
            ev['snapshot']=snapshot;ev['session_context']=KI.company_review.session_context.build(snapshot)
        context={'sources':sources or [],'cutoff':ev['snapshot']['acquired_at'],
                 'issuer_identity':{'aliases':['Emitent']}}
        context['analysis_manifest']=KI.build_analysis_manifest(ev,context)
        context['analysis_manifest']['review_contract']=grounded.CONTRACT
        context['ai_preflight']=KI.automatic_ai_preflight(ev,context)
        request=KI.event_analysis_request(ev,context);context['prepared_ai_request']=request
        return f,ev,context,request

    def choice(self,request,attention='INFORM'):
        book=json.loads(request['messages'][-1]['content'])['evidence_review']
        support='S_ALIGNMENT' if 'S_ALIGNMENT' in book['supports'] else 'S_DETECTION'
        limit='L_ACTIVITY_SCOPE' if 'L_ACTIVITY_SCOPE' in book['limits'] else 'L_FUTURE'
        return {'verdict':attention,
                'price_evidence':next(iter(book['price'])),'momentum_evidence':[next(iter(book['momentum']))],
                'supporting_evidence':[support],'limiting_evidence':[limit],
                'watch_condition':next(iter(book['conditions'])),'source_quote':'NONE'}

    def body(self,wire):
        return {'model':'offline-evidence-test','usage':{'total_tokens':1},
                'choices':[{'finish_reason':'stop','message':{'content':json.dumps(wire)}}]}

    def test_request_has_only_code_enums_preserves_full_data_and_keeps_budget(self):
        f,ev,ctx,request=self.sample();before=copy.deepcopy((ev,ctx))
        self.assertEqual(request['response_format']['json_schema']['name'],grounded.SCHEMA_NAME)
        self.assertEqual((request['model'],request['max_completion_tokens']),('gpt-4o-mini',3000))
        payload=json.loads(request['messages'][-1]['content'])
        self.assertEqual(payload['proved_event']['analysis_manifest']['session_context'],ev['session_context'])
        self.assertIn('evidence_review',payload)
        self.assertNotIn('assessment: obiekt',request['messages'][0]['content'])
        self.assertIn('Nie porównuj jej z innymi',request['messages'][0]['content'])
        self.assertEqual(KI.event_analysis_request(ev,ctx),request)
        self.assertEqual((ev,ctx),before)
        jsonschema.validate(self.choice(request),request['response_format']['json_schema']['schema'])

    def test_shortened_bar_full_session_and_rsi_classification_are_rendered_from_data(self):
        s=shortened.snapshot();s['indicators']['rsi']=40.
        s['indicators'].update(ma_fast=s['price']+.1,last_macd_hist=-.1,plus_di=10.,minus_di=30.)
        s['price_matrix'].update(anchor_price=2.,change_pct=(s['price']/2.-1)*100)
        s['spread']={'bid':2.,'ask':1.,'freshness_confirmed':False}
        f,ev,ctx,request=self.sample(s)
        wire=self.choice(request);wire['momentum_evidence']=['M_RSI_BELOW']
        canonical,proof=grounded.decode(KI,wire,s,ctx)
        clean=KI.validate_event_analysis(canonical,s,ctx)
        self.assertFalse(KI.analysis_publication_issues(clean,True),clean.get('quality_issues'))
        self.assertIn('skróconym',clean['assessment']['activity'])
        self.assertIn('poniżej średniej godzinowej',clean['assessment']['activity'])
        self.assertIn('sesji',clean['assessment']['movement'])
        self.assertIn('niespójne',clean['assessment']['risk'])
        self.assertNotIn('wyprzedania',clean['technical'][1]['interpretation'])
        self.assertEqual(proof['selected'],wire)
        self.assertEqual(s['rvol'],None)

    def test_inventor_sentiment_cause_and_free_narrative_cannot_enter_response(self):
        f,ev,ctx,request=self.sample();schema=request['response_format']['json_schema']['schema']
        for field,value in (('price_evidence','Pozytywny sentyment inwestorów.'),
                            ('momentum_evidence',['RSI dowodzi przewartościowania.']),
                            ('supporting_evidence',['Zainteresowanie inwestorów wspiera kontynuację.'])):
            wire=self.choice(request);wire[field]=value
            with self.assertRaises(jsonschema.ValidationError):jsonschema.validate(wire,schema)
            with self.assertRaises(ValueError):grounded.decode(KI,wire,ev['snapshot'],ctx)
        wire=self.choice(request);wire['assessment']={'movement':'Wzrost wynika z wyników finansowych.'}
        with self.assertRaises(ValueError):grounded.decode(KI,wire,ev['snapshot'],ctx)

    def test_frozen_catalogue_is_checked_against_saved_input_and_unknown_codes_fail(self):
        f,ev,ctx,request=self.sample();wire=self.choice(request)
        changed=copy.deepcopy(ctx);payload=json.loads(changed['prepared_ai_request']['messages'][-1]['content'])
        payload['evidence_review']['axes']['movement']='Niepotwierdzona cudza treść.'
        changed['prepared_ai_request']['messages'][-1]['content']=json.dumps(payload)
        with self.assertRaisesRegex(ValueError,'Katalog dowodów'):grounded.decode(KI,wire,ev['snapshot'],changed)
        wire['momentum_evidence']=['M_RSI_HIGH']
        if 'M_RSI_HIGH' not in json.loads(request['messages'][-1]['content'])['evidence_review']['momentum']:
            with self.assertRaises(ValueError):grounded.decode(KI,wire,ev['snapshot'],ctx)

    def test_ai_may_choose_panel_only_despite_alignment_with_no_positive_override(self):
        f,ev,ctx,request=self.sample()
        wire=self.choice(request,'PANEL_ONLY')
        analysis,proof=grounded.decode(KI,wire,ev['snapshot'],ctx)
        clean=KI.validate_event_analysis(analysis,ev['snapshot'],ctx)
        self.assertFalse(KI.analysis_publication_issues(clean,True),clean.get('quality_issues'))
        self.assertEqual(clean['final_review']['attention'],'PANEL_ONLY')
        self.assertIn('Tylko panel',clean['final_review']['explanation'])

    def test_reason_categories_and_repeated_identifiers_are_rejected(self):
        f,ev,ctx,request=self.sample();wire=self.choice(request)
        wire['limiting_evidence']=['S_DETECTION']
        with self.assertRaises(ValueError):grounded.decode(KI,wire,ev['snapshot'],ctx)
        wire=self.choice(request);wire['momentum_evidence']*=2
        with self.assertRaisesRegex(ValueError,'powtórzyło'):grounded.decode(KI,wire,ev['snapshot'],ctx)

    def test_one_mock_call_keeps_raw_ids_and_decision_provenance_and_can_deliver(self):
        f,ev,ctx,request=self.sample();wire=self.choice(request);body=self.body(wire)
        with f.store.transaction() as db:
            db.execute("UPDATE analysis_jobs SET state='PENDING_AI',context=?",(KI.json_text(ctx),))
        before=copy.deepcopy(body)
        with patch.object(KI,'service_http',return_value=body) as model:
            self.assertTrue(KI.process_analysis_once(f.store,{'OPENAI_API_KEY':'fake'}));model.assert_called_once()
        job=f.rows('analysis_jobs')[0];self.assertEqual(job['state'],'DONE',job['last_error'])
        saved=KI.load_payload(job['result'])
        self.assertEqual(saved['provider']['raw_response'],before)
        self.assertEqual(saved['provider']['evidence_review']['selected'],wire)
        self.assertEqual(saved['analysis']['hypotheses'],[])
        self.assertTrue(KI.company_review.finalize(KI,f.store,fixtures.NOW))
        import selected_opportunities as top
        view=top.collect(KI,f.store,fixtures.NOW)
        self.assertEqual(len(view['rising_watch']),1,view)
        self.assertEqual(view['rising_watch'][0]['evidence_review']['selected'],wire)
        self.assertIn('opis składa KI',top.cards_html(KI,view['rising_watch'],fixtures.NOW))
        receipt={'ok':True,'result':{'message_id':789,'chat':{'id':456}}}
        with patch.object(KI,'service_http',return_value=receipt) as telegram:
            self.assertTrue(KI.process_delivery_once(f.store,{'TELEGRAM_BOT_TOKEN':'fake','TELEGRAM_CHAT_ID':'456'}))
            telegram.assert_called_once()
        self.assertEqual(f.rows('outbox')[0]['status'],'DELIVERED')

    def test_legacy_prepared_response_is_not_rewritten_or_upgraded(self):
        f=fixtures.FinalCompanyReviewTests();f.setUp();self.addCleanup(f.doCleanups);f.prepare(1)
        ev=KI.load_payload(f.rows('events')[0]['payload'])
        ctx={'sources':[]};ctx['analysis_manifest']=KI.build_analysis_manifest(ev,ctx)
        ctx['ai_preflight']=KI.automatic_ai_preflight(ev,ctx)
        request=KI.event_analysis_request(ev,ctx);ctx['prepared_ai_request']=request
        body=self.body(f.answer());raw=body['choices'][0]['message']['content']
        analysis,metadata=KI.parse_event_analysis_response(body,ev['snapshot'],ctx)
        self.assertNotIn('evidence_review',metadata)
        self.assertEqual(metadata['raw_response']['choices'][0]['message']['content'],raw)
        self.assertFalse(KI.analysis_publication_issues(analysis,True))

    def test_foreign_identity_or_timestamp_cannot_reuse_frozen_catalogue(self):
        f,ev,ctx,request=self.sample();wire=self.choice(request)
        for key,value in (('ticker','OTHER'),('currency','USD'),('acquired_at','2020-01-01T00:00:00+00:00')):
            snap=copy.deepcopy(ev['snapshot'])
            if snap.get(key)==value:value='OTHER'
            snap[key]=value
            with self.assertRaisesRegex(ValueError,'Tożsamość lub czas'):
                grounded.decode(KI,wire,snap,ctx)

    def test_model_chooses_only_verified_source_ids_without_quote_text_in_schema(self):
        source={'id':'S1','content':'Emitent opublikował raport dotyczący przebiegu badań klinicznych.',
                'published_at':fixtures.NOW.isoformat(),'url':'https://example.org/report'}
        f,ev,ctx,request=self.sample(sources=[source]);wire=self.choice(request);wire['source_quote']='Q1'
        self.assertNotIn(source['content'],json.dumps(request['response_format']))
        analysis,metadata=KI.parse_event_analysis_response(self.body(wire),ev['snapshot'],ctx)
        self.assertEqual(analysis['context'],[{'source_id':'S1','fact':source['content']}])
        self.assertFalse(KI.analysis_publication_issues(analysis,True))

    def test_rsi_extreme_codes_exist_only_for_the_measured_class(self):
        for rsi,expected in ((29.9,'M_RSI_LOW'),(30.,'M_RSI_BELOW'),(70.,'M_RSI_ABOVE'),(70.1,'M_RSI_HIGH')):
            s=shortened.snapshot();s['indicators']['rsi']=rsi
            f,ev,ctx,request=self.sample(s)
            book=json.loads(request['messages'][-1]['content'])['evidence_review']
            self.assertIn(expected,book['momentum'])
            self.assertEqual('L_RSI_EXTREME' in book['limits'],rsi<30 or rsi>70)
            self.assertEqual(len([c for c in book['momentum'] if c.startswith('M_RSI_')]),1)

    def test_quote_states_stay_distinct_in_checked_report(self):
        for quote,word in (({},'Brak bid/ask'),({'bid':1.5},'niepełne'),
                           ({'bid':2.,'ask':1.},'niespójne'),({'bid':1.5,'ask':1.6},'dostępne')):
            s=shortened.snapshot();s['spread']={**quote,'freshness_confirmed':False}
            f,ev,ctx,request=self.sample(s)
            analysis,proof=grounded.decode(KI,self.choice(request),s,ctx)
            clean=KI.validate_event_analysis(analysis,s,ctx)
            self.assertFalse(KI.analysis_publication_issues(clean,True),clean.get('quality_issues'))
            self.assertIn(word,clean['assessment']['risk'])
            if word=='dostępne':self.assertNotIn('Brak bid/ask',clean['assessment']['risk'])


if __name__=='__main__':unittest.main()
