"""Observed all-PANEL failure, explicit main evidence and legacy frozen jobs; no API."""
import copy
import json
import unittest
from unittest.mock import patch
import jsonschema
import KI
import evidence_review as grounded
import review_coordinator as coordinator
import test_evidence_review_20261109 as previous
import test_final_company_review_20261106 as fixtures


class ReviewCoordinatorTests(unittest.TestCase):
    def sample(self,snapshot=None,sources=None):
        old=previous.EvidenceReviewTests();self.addCleanup(old.doCleanups)
        f,ev,ctx,request=old.sample(snapshot,sources)
        ctx['analysis_manifest']['review_contract']=grounded.CURRENT_CONTRACT
        request=KI.event_analysis_request(ev,ctx);ctx['prepared_ai_request']=request
        book=json.loads(request['messages'][-1]['content'])['evidence_review']
        return f,ev,ctx,request,book

    def wire(self,book,attention='INFORM',reason=None,quote='NONE'):
        rules=book['coordination']
        reason=reason or (rules['inform_reasons'] if attention=='INFORM' else rules['panel_reasons'])[0]
        supports=[rules['inform_reasons'][0]]
        limits=['L_FUTURE']
        if reason in book['supports'] and reason not in supports:supports.append(reason)
        if reason in book['limits'] and reason not in limits:limits.append(reason)
        return {'price_evidence':next(iter(book['price'])),
                'momentum_evidence':[next(iter(book['momentum']))],
                'supporting_evidence':supports,'limiting_evidence':limits,
                'watch_condition':next(iter(book['conditions'])),
                'decision':{'verdict':attention,'primary_reason':reason,'source_quote':quote}}

    def body(self,wire):
        return {'model':'offline-coordinator','usage':{'total_tokens':1},
                'choices':[{'finish_reason':'stop','message':{'content':json.dumps(wire)}}]}

    def panel_sample(self):
        f,ev,ctx,request,book=self.sample();snap=copy.deepcopy(ev['snapshot'])
        first=snap['chart_history'][0]
        first['open']=snap['price']+3.;first['high']=max(first['high'],first['open'])
        return self.sample(snapshot=snap)

    def test_today_general_future_reason_cannot_reject_an_aligned_signal(self):
        f,ev,ctx,request,book=self.sample()
        for code in ('L_FUTURE','L_CAUSE','L_ACTIVITY_SCOPE','L_QUOTES','L_FUNDAMENTALS','L_PLAN'):
            wire=self.wire(book,'PANEL_ONLY',code)
            with self.subTest(code=code):
                with self.assertRaises(jsonschema.ValidationError):jsonschema.validate(wire,request['response_format']['json_schema']['schema'])
                with self.assertRaisesRegex(ValueError,'konkretnej'):grounded.decode(KI,wire,ev['snapshot'],ctx)

    def test_positive_observation_keeps_unknown_future_open_hour_and_quote_caveats(self):
        f,ev,ctx,request,book=self.sample();wire=self.wire(book)
        jsonschema.validate(wire,request['response_format']['json_schema']['schema'])
        analysis,proof=KI.parse_event_analysis_response(self.body(wire),ev['snapshot'],ctx)
        self.assertFalse(KI.analysis_publication_issues(analysis,True),analysis.get('quality_issues'))
        self.assertEqual(analysis['final_review']['attention'],'INFORM')
        self.assertIn('Do obserwacji',analysis['final_review']['explanation'])
        self.assertIn('częściowy',analysis['assessment']['activity'])
        self.assertIn('Dalszy kierunek pozostaje nieustalony',analysis['assessment']['risk'])
        self.assertEqual(proof['evidence_review']['selected'],wire)

    def test_panel_still_allowed_for_opposite_intraday_direction_without_positive_override(self):
        f,ev,ctx,request,book=self.panel_sample()
        self.assertIn('L_SESSION',book['coordination']['panel_reasons'])
        wire=self.wire(book,'PANEL_ONLY','L_SESSION')
        jsonschema.validate(wire,request['response_format']['json_schema']['schema'])
        analysis,proof=KI.parse_event_analysis_response(self.body(wire),ev['snapshot'],ctx)
        self.assertFalse(KI.analysis_publication_issues(analysis,True),analysis.get('quality_issues'))
        self.assertEqual(analysis['final_review']['attention'],'PANEL_ONLY')
        self.assertTrue(analysis['final_review']['explanation'].startswith('Tylko panel: '+book['limits']['L_SESSION']))
        self.assertNotIn('Tylko panel: Dalszy kierunek',analysis['final_review']['explanation'])

    def test_decision_comes_after_evidence_and_uses_supported_nested_objects(self):
        f,ev,ctx,request,book=self.sample();schema=request['response_format']['json_schema']['schema']
        self.assertEqual(schema['type'],'object');self.assertNotIn('anyOf',schema)
        self.assertEqual(list(schema['properties'])[-1],'decision')
        self.assertEqual(set(schema['required']),set(schema['properties']))
        self.assertNotIn('Pierwszy limiting_evidence',request['messages'][0]['content'])
        self.assertIn('obserwacji w XTB',request['messages'][0]['content'])
        self.assertEqual((request['model'],request['max_completion_tokens']),('gpt-4o-mini',3000))

    def test_primary_reason_must_be_in_the_selected_evidence(self):
        f,ev,ctx,request,book=self.panel_sample();wire=self.wire(book,'PANEL_ONLY','L_SESSION')
        wire['limiting_evidence']=['L_FUTURE']
        with self.assertRaisesRegex(ValueError,'konkretnej'):grounded.decode(KI,wire,ev['snapshot'],ctx)

    def source(self):
        return {'id':'S1','content':'Emitent poinformował o wstrzymaniu rekrutacji do badania klinicznego.',
                'published_at':fixtures.NOW.isoformat(),'url':'https://example.org/report'}

    def test_negative_source_can_support_panel_without_claiming_the_cause_of_price_move(self):
        source=self.source();f,ev,ctx,request,book=self.sample(sources=[source])
        quote=next(iter(book['quotes']));wire=self.wire(book,'PANEL_ONLY','SOURCE_EVENT',quote)
        jsonschema.validate(wire,request['response_format']['json_schema']['schema'])
        analysis,proof=KI.parse_event_analysis_response(self.body(wire),ev['snapshot'],ctx)
        self.assertEqual(analysis['final_review']['attention'],'PANEL_ONLY')
        self.assertEqual(analysis['context'],[{'source_id':'S1','fact':source['content']}])
        self.assertFalse(KI.analysis_publication_issues(analysis,True),analysis.get('quality_issues'))
        self.assertNotIn(source['content'],json.dumps(request['response_format']))

    def test_source_reason_cannot_be_used_without_a_known_quote(self):
        f,ev,ctx,request,book=self.sample(sources=[self.source()])
        for quote in ('NONE','Q999'):
            wire=self.wire(book,'PANEL_ONLY','SOURCE_EVENT',quote)
            with self.subTest(quote=quote):
                with self.assertRaises(jsonschema.ValidationError):jsonschema.validate(wire,request['response_format']['json_schema']['schema'])
                with self.assertRaises(ValueError):grounded.decode(KI,wire,ev['snapshot'],ctx)

    def test_material_local_risk_still_blocks_inform(self):
        f,ev,ctx,request,book=self.sample();snap=copy.deepcopy(ev['snapshot'])
        snap['ohlc']['high']=snap['price']*1.1
        for row in snap['chart_history']:
            if row['time']==snap['candle_time']:row['high']=snap['ohlc']['high']
        f,ev,ctx,request,book=self.sample(snapshot=snap)
        self.assertEqual(book['local_verdict'],'RISK_DOMINANT')
        wire=self.wire(book,'INFORM','S_DETECTION')
        with self.assertRaises(jsonschema.ValidationError):jsonschema.validate(wire,request['response_format']['json_schema']['schema'])
        with self.assertRaisesRegex(ValueError,'omijać'):grounded.decode(KI,wire,ev['snapshot'],ctx)

    def test_observation_does_not_require_a_complete_buy_order_plan(self):
        book={'local_verdict':'ALIGNED','supports':{'S_DETECTION':'proof','S_ALIGNMENT':'aligned'},
              'limits':{'L_FUTURE':'unknown','L_PLAN':'no long plan','L_RSI_EXTREME':'extreme'},'quotes':{}}
        for change in (-3.,3.):
            rules=coordinator.policy(book,{'candle_status':'OPEN','price_matrix':{'change_pct':change}})
            self.assertEqual(rules['panel_reasons'],[])
            self.assertIn('L_PLAN',rules['context_only']);self.assertIn('L_RSI_EXTREME',rules['context_only'])

    def test_low_measured_hourly_volume_differs_from_a_partial_hour(self):
        book={'supports':{'S_ALIGNMENT':'aligned'},'limits':{'L_ACTIVITY_LOW':'low'},'quotes':{}}
        opened=coordinator.policy(book,{'candle_status':'OPEN'})
        closed=coordinator.policy(book,{'candle_status':'CLOSED'})
        self.assertNotIn('L_ACTIVITY_LOW',opened['panel_reasons'])
        self.assertIn('L_ACTIVITY_LOW',closed['panel_reasons'])

    def test_one_model_call_can_reach_one_digest_and_top5_without_real_delivery(self):
        f,ev,ctx,request,book=self.sample();wire=self.wire(book);body=self.body(wire);original=copy.deepcopy(body)
        with f.store.transaction() as db:db.execute("UPDATE analysis_jobs SET state='PENDING_AI',context=?",(KI.json_text(ctx),))
        with patch.object(KI,'service_http',return_value=body) as model:
            self.assertTrue(KI.process_analysis_once(f.store,{'OPENAI_API_KEY':'fake'}));model.assert_called_once()
        job=f.rows('analysis_jobs')[0];self.assertEqual(job['state'],'DONE',job['last_error'])
        result=KI.load_payload(job['result'])
        self.assertEqual(result['provider']['raw_response'],original)
        self.assertEqual(result['provider']['evidence_review']['contract'],coordinator.CONTRACT)
        self.assertTrue(KI.company_review.finalize(KI,f.store,fixtures.NOW))
        self.assertEqual(len(f.rows('outbox')),1)
        import selected_opportunities
        self.assertEqual(len(selected_opportunities.collect(KI,f.store,fixtures.NOW)['rising_watch']),1)
        receipt={'ok':True,'result':{'message_id':789,'chat':{'id':456}}}
        with patch.object(KI,'service_http',return_value=receipt) as telegram:
            self.assertTrue(KI.process_delivery_once(f.store,{'TELEGRAM_BOT_TOKEN':'fake','TELEGRAM_CHAT_ID':'456'}))
            telegram.assert_called_once()
        self.assertEqual(f.rows('outbox')[0]['status'],'DELIVERED')

    def test_specific_panel_decision_never_forces_a_notification(self):
        f,ev,ctx,request,book=self.panel_sample();wire=self.wire(book,'PANEL_ONLY','L_SESSION')
        with f.store.transaction() as db:
            db.execute('UPDATE events SET payload=?',(KI.json_text(ev),))
            db.execute("UPDATE analysis_jobs SET state='PENDING_AI',context=?",(KI.json_text(ctx),))
        with patch.object(KI,'service_http',return_value=self.body(wire)):
            self.assertTrue(KI.process_analysis_once(f.store,{'OPENAI_API_KEY':'fake'}))
        job=f.rows('analysis_jobs')[0]
        self.assertEqual(job['state'],'DONE',job['last_error'])
        self.assertTrue(KI.company_review.finalize(KI,f.store,fixtures.NOW))
        self.assertEqual(f.rows('outbox'),[])


if __name__=='__main__':unittest.main()
