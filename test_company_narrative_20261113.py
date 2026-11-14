import copy
import unittest
import company_narrative as narrative


def fixture_narrative():
    texts={
        'summary':'Cena [price] wymaga oceny razem z kierunkiem trendu; sam ruch nie rozstrzyga kontynuacji.',
        'technical':'Cena [price] stanowi punkt odniesienia dla zapisanych wskaźników i ich sprzeczności.',
        'activity':'Aktywność przy cenie [price] należy ocenić na porównywalnych zamkniętych przedziałach.',
        'levels':'Cena [price] jest podstawą porównania z zapisanymi poziomami, bez tworzenia nowych celów.',
        'horizon':'Horyzont pozostaje warunkową interpretacją struktury, a nie terminem realizacji.',
        'risks':'Brak potwierdzenia warunków wykonania ogranicza wykorzystanie scenariusza.',
        'context':'Przyczyna ruchu pozostaje nieustalona, jeśli nie ma przyjętego faktu źródłowego.'}
    return {key:{'text':text,'references':['price'] if '[price]' in text else []} for key,text in texts.items()}


class NarrativeTests(unittest.TestCase):
    def setUp(self):
        self.snapshot={'price':4.64,'currency':'USD','acquired_at':'2026-11-13T19:20:00+00:00','indicators':{'rsi':55.}}
        self.facts=narrative.facts_for(self.snapshot,{})

    def test_authored_text_kept_with_real_numeric_substitution(self):
        wire=fixture_narrative();wire['technical']={'text':'Cena [price] i RSI [indicator.rsi] wskazują różne aspekty układu; bez struktury nie przesądzają kontynuacji.','references':['price','indicator.rsi']}
        result=narrative.checked(wire,self.facts)
        self.assertEqual(result['status'],'COMPLETE');self.assertIn('4,64 USD',result['sections']['technical']['text'])
        self.assertIn('różne aspekty',result['sections']['technical']['text'])

    def test_unknown_reference_drops_only_affected_section(self):
        wire=fixture_narrative();wire['technical']={'text':'Cena [unknown] ma znaczenie dla oceny.','references':['unknown']}
        result=narrative.checked(wire,self.facts)
        self.assertEqual(result['status'],'PARTIAL');self.assertNotIn('technical',result['sections']);self.assertIn('summary',result['sections'])

    def test_own_number_or_unicode_digit_is_not_allowed(self):
        for value in ('Cena wzrośnie o 100 procent.','Cena wzrośnie o ٢ procent.'):
            wire=fixture_narrative();wire['horizon']={'text':value,'references':[]}
            self.assertNotIn('horizon',narrative.checked(wire,self.facts)['sections'])

    def test_refs_must_match_text(self):
        wire=fixture_narrative();wire['summary']['references']=[]
        self.assertNotIn('summary',narrative.checked(wire,self.facts)['sections'])

    def test_unsafe_output_is_escaped_not_executed(self):
        wire=fixture_narrative();wire['risks']['text']='Zapis <script>alert("x")</script> nie jest instrukcją.'
        markup=narrative.html(narrative.checked(wire,self.facts))
        self.assertNotIn('<script>',markup);self.assertIn('&lt;script&gt;',markup)

    def test_no_guaranteed_profit_or_imperative(self):
        for value in ('To na pewno wzrośnie i gwarantuje zysk.','Kup teraz, bo to jedyna okazja.'):
            wire=fixture_narrative();wire['summary']['text']=value+' Cena [price].'
            self.assertNotIn('summary',narrative.checked(wire,self.facts)['sections'])

    def test_no_mutation_of_source_data_or_response(self):
        wire=fixture_narrative();before=copy.deepcopy((wire,self.facts))
        narrative.checked(wire,self.facts);self.assertEqual((wire,self.facts),before)

    def test_null_is_not_zero_and_volume_scope_is_explicit(self):
        snapshot={**self.snapshot,'previous_closed':{'volume':1000,'average_volume':500,'rvol':2},'rvol':None,'candle_status':'OPEN'}
        facts=narrative.facts_for(snapshot,{})
        self.assertNotIn('current.rvol',facts);self.assertEqual(facts['closed.rvol']['value'],2)
        self.assertIn('zamknięta',facts['closed.volume']['scope'])

    def test_compaction_preserves_every_daily_value(self):
        material={'daily_candles':[{'time':'2026-11-12','close':4.64,'volume':1000},{'time':'2026-11-13','close':4.8,'volume':2000}]}
        compact=narrative.compact_input(material)['daily_candles']
        self.assertEqual([dict(zip(compact['columns'],row)) for row in compact['rows']],material['daily_candles'])

    def test_real_final_contract_has_authored_text_and_one_provider_call(self):
        import json
        from unittest.mock import patch
        import KI
        import test_review_coordinator_20261110 as helpers
        test=helpers.ReviewCoordinatorTests();self.addCleanup(test.doCleanups)
        _,ev,ctx,request,book=test.sample();wire=test.wire(book)
        wire['narrative']['summary']['text']='Cena [price] wymaga zestawienia z oporem; ruch może osłabnąć, jeśli poziom nie zostanie utrzymany.'
        analysis,proof=KI.parse_event_analysis_response(test.body(wire),ev['snapshot'],ctx)
        report=proof['evidence_review']['narrative']
        self.assertEqual(report['status'],'COMPLETE');self.assertIn('może osłabnąć',report['sections']['summary']['text'])
        self.assertEqual(request['model'],'gpt-4o-mini')
        self.assertIn('narrative',request['response_format']['json_schema']['schema']['required'])

    def test_new_contract_requires_valid_verdict_and_risk_without_repair(self):
        import KI
        import test_review_coordinator_20261110 as helpers
        test=helpers.ReviewCoordinatorTests();self.addCleanup(test.doCleanups)
        _,ev,ctx,request,book=test.sample();wire=test.wire(book)
        wire['narrative']['summary']['text']='Cena [invented] będzie rosła.'
        wire['narrative']['summary']['references']=['invented']
        with self.assertRaises(KI.AnalysisRejected):KI.parse_event_analysis_response(test.body(wire),ev['snapshot'],ctx)

    def test_old_frozen_coordinated_job_is_still_decoded_without_rewriting(self):
        import json
        import KI
        import test_review_coordinator_20261110 as helpers
        test=helpers.ReviewCoordinatorTests();self.addCleanup(test.doCleanups)
        _,ev,ctx,request,book=test.sample();wire=test.wire(book);wire.pop('narrative')
        frozen=copy.deepcopy(request);payload=json.loads(frozen['messages'][-1]['content']);payload.pop('narrative_facts')
        frozen['messages'][-1]['content']=KI.json_text(payload)
        properties=frozen['response_format']['json_schema']['schema'];properties['properties'].pop('narrative');properties['required'].remove('narrative')
        ctx['prepared_ai_request']=frozen
        _,proof=KI.parse_event_analysis_response(test.body(wire),ev['snapshot'],ctx)
        self.assertNotIn('narrative',proof['evidence_review'])

    def test_investor_story_and_rsi_valuation_without_source_are_not_facts(self):
        for text,refs in (('Wzrost wynika z euforii inwestorów, a cena to [price].',['price']),
                          ('RSI [indicator.rsi] dowodzi niedowartościowania spółki.',['indicator.rsi'])):
            wire=fixture_narrative();wire['technical']={'text':text,'references':refs}
            self.assertNotIn('technical',narrative.checked(wire,self.facts)['sections'])

    def test_full_year_request_preserves_all_rows_within_existing_packet_cap(self):
        import KI
        import large_movement
        import test_large_movement_20261113 as helpers
        fixture=helpers.LargeMovementTests();fixture.setUp();self.addCleanup(fixture.doCleanups)
        rows=helpers.daily_sample(250)
        packet=large_movement.packet(KI,fixture.store,fixture.s,rows,large_movement.setup(fixture.s,rows))
        prepared=large_movement.request(KI,packet)
        import json
        payload=json.loads(prepared['messages'][-1]['content'])
        self.assertEqual(len(payload['daily_candles']['rows']),250)
        self.assertLess(len(KI.json_text(prepared).encode()),160000)

    def test_supplemental_indicators_and_scenario_levels_are_referenceable(self):
        snap={**self.snapshot,'supplemental_indicators':{'vwap':4.5,'stoch_rsi_k':23.,'stoch_rsi_d':21.,'fibonacci':[4.6,4.4]}}
        material={'analysis_manifest':{'scenario_plan':{'levels':{'guard':4.78},'condition':{'level':4.78}}}}
        facts=narrative.facts_for(snap,material)
        self.assertEqual(facts['supplement.vwap']['value'],4.5)
        self.assertEqual(facts['supplement.fibonacci.1']['value'],4.4)
        self.assertEqual(facts['scenario.condition.level']['value'],4.78)

if __name__=='__main__':unittest.main()
