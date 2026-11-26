import copy
import unittest
import company_narrative as narrative


def fixture_narrative(full=False):
    texts={
        'summary':'Cena [price] wymaga oceny razem z kierunkiem trendu; sam ruch nie rozstrzyga kontynuacji.',
        'data_quality':'Cena [price] jest dostępna, a zakres pozostałych danych należy oceniać osobno dla każdego wniosku.',
        'technical':'Cena [price] stanowi punkt odniesienia dla zapisanych wskaźników i ich sprzeczności.',
        'momentum':'Cena [price] wymaga zestawienia z dostępnymi wskaźnikami momentum, bez rozstrzygania na podstawie jednego z nich.',
        'activity':'Aktywność przy cenie [price] należy ocenić na porównywalnych zamkniętych przedziałach.',
        'levels':'Cena [price] jest podstawą porównania z zapisanymi poziomami, bez tworzenia nowych celów.',
        'horizon':'Horyzont pozostaje warunkową interpretacją struktury, a nie terminem realizacji.',
        'fundamentals':'Brak przyjętych danych finansowych ogranicza wyłącznie ocenę fundamentalną, a nie pomiar ceny [price].',
        'scenarios':'Cena [price] wymaga warunkowego wariantu wzrostowego, neutralnego i spadkowego z istniejących poziomów.',
        'risks':'Brak potwierdzenia warunków wykonania ogranicza wykorzystanie scenariusza.',
        'context':'Przyczyna ruchu pozostaje nieustalona, jeśli nie ma przyjętego faktu źródłowego.'}
    allowed=narrative.FULL_SECTIONS if full else narrative.SECTIONS
    result={}
    for key in allowed:
        text=texts[key]
        if full and '[price]' not in text:text+=' Cena [price] pozostaje punktem odniesienia.'
        result[key]={'text':text,'references':['price'] if '[price]' in text else []}
    return result


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
        self.assertEqual(result['rejected_sections']['technical']['reason'],'Nieznane odwołanie do danych.')

    def test_provider_schema_allows_only_real_fact_ids(self):
        shape=narrative.schema(self.facts)
        items=shape['properties']['technical']['properties']['references']['items']
        self.assertEqual(set(items['enum']),set(self.facts))
        self.assertNotIn('activity',items['enum'])

    def test_own_number_or_unicode_digit_is_not_allowed(self):
        for value in ('Cena wzrośnie o 100 procent.','Cena wzrośnie o ٢ procent.'):
            wire=fixture_narrative();wire['horizon']={'text':value,'references':[]}
            self.assertNotIn('horizon',narrative.checked(wire,self.facts)['sections'])

    def test_numeric_prose_with_separate_valid_references_is_accepted(self):
        facts=narrative.facts_for({**self.snapshot,'indicators':{'rsi':75.48,'ma_fast':.82,'ma_slow':.74}}, {})
        wire=fixture_narrative()
        wire['technical']={
            'text':'Cena 4,64 USD jest powyżej SMA 10 wynoszącej 0,82 USD, lecz RSI 75,48 wskazuje wykupienie i zwiększa ryzyko korekty.',
            'references':['price','indicator.ma_fast','indicator.rsi']}
        result=narrative.checked(wire,facts)
        self.assertIn('technical',result['sections'])

    def test_numeric_prose_rejects_number_missing_from_referenced_facts(self):
        facts=narrative.facts_for({**self.snapshot,'indicators':{'rsi':75.48,'ma_fast':.82}}, {})
        wire=fixture_narrative()
        wire['technical']={
            'text':'Cena 4,64 USD jest powyżej SMA 10 wynoszącej 0,82 USD, a nieistniejący cel to 9,99 USD.',
            'references':['price','indicator.ma_fast']}
        self.assertNotIn('technical',narrative.checked(wire,facts)['sections'])

    def test_refs_must_match_text(self):
        wire=fixture_narrative();wire['summary']['references']=[]
        self.assertNotIn('summary',narrative.checked(wire,self.facts)['sections'])

    def test_explicit_price_comparison_is_checked_against_both_averages(self):
        facts=narrative.facts_for({**self.snapshot,'indicators':{'ma_fast':5.,'ma_slow':6.}}, {})
        wire=fixture_narrative()
        wire['technical']={'text':'Cena [price] pozostaje powyżej obu średnich [indicator.ma_fast] oraz [indicator.ma_slow], co wspiera wzrost.',
                           'references':['price','indicator.ma_fast','indicator.ma_slow']}
        result=narrative.checked(wire,facts)
        self.assertNotIn('technical',result['sections'])
        self.assertIn('summary',result['sections'])
        wire['technical']['text']=wire['technical']['text'].replace('powyżej','poniżej').replace('wzrost','spadek')
        self.assertIn('technical',narrative.checked(wire,facts)['sections'])

    def test_general_price_below_ma_wording_is_also_checked(self):
        facts=narrative.facts_for({**self.snapshot,'price':2.07,'indicators':{'ma_fast':2.061,'ma_slow':2.07}}, {})
        wire=fixture_narrative()
        wire['technical']={'text':'Cena [price] znajduje się poniżej średnich MA [indicator.ma_fast] i [indicator.ma_slow], co wskazuje na spadkowy trend.',
                           'references':['price','indicator.ma_fast','indicator.ma_slow']}
        self.assertNotIn('technical',narrative.checked(wire,facts)['sections'])

    def test_mixed_short_trend_cannot_be_called_direct_further_decline(self):
        facts=narrative.facts_for({**self.snapshot,'trend_context':{'horizons':{'short':{'direction':'MIXED'}}}}, {})
        wire=fixture_narrative()
        wire['horizon']={'text':'Horyzont krótkoterminowy [trend.short.direction] wskazuje na dalsze spadki.',
                         'references':['trend.short.direction']}
        result=narrative.checked(wire,facts)
        self.assertNotIn('horizon',result['sections'])
        self.assertIn('sprzeczny',result['rejected_sections']['horizon']['reason'])

    def test_data_quality_facts_separate_full_year_from_available_history(self):
        rows=[{'time':'2026-07-01T00:00:00+00:00','high':2.,'low':1.,'close':1.5,'volume':100},
              {'time':'2026-11-24T00:00:00+00:00','high':2.2,'low':1.2,'close':2.,'volume':200}]
        facts=narrative.facts_for(self.snapshot,{'daily_candles':rows})
        self.assertEqual(facts['quality.daily_coverage']['value'],'AVAILABLE_HISTORY')
        self.assertEqual(facts['quality.daily_sessions']['value'],2)

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
        self.assertEqual(request['model'],'gpt-6-luna')
        self.assertEqual(request['reasoning_effort'],'none')
        self.assertIn('narrative',request['response_format']['json_schema']['schema']['required'])

    def test_new_contract_keeps_canonical_verdict_when_authored_section_is_invalid(self):
        import KI
        import test_review_coordinator_20261110 as helpers
        test=helpers.ReviewCoordinatorTests();self.addCleanup(test.doCleanups)
        _,ev,ctx,request,book=test.sample();wire=test.wire(book)
        wire['narrative']['summary']['text']='Cena [invented] będzie rosła.'
        wire['narrative']['summary']['references']=['invented']
        analysis,proof=KI.parse_event_analysis_response(test.body(wire),ev['snapshot'],ctx)
        report=proof['evidence_review']['narrative']
        self.assertEqual(analysis['final_review']['attention'],'INFORM')
        self.assertEqual(report['status'],'PARTIAL')
        self.assertNotIn('summary',report['sections'])

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
