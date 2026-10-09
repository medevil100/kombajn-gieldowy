"""Etap C: kontrakty czystych funkcji i dane jawne, bez podmian API i bez mockow."""
import unittest
import KI


def snapshot(ticker='STX.WA', company='Stalexport Autostrady S.A.'):
    return {
        'ticker':ticker,'company_name':company,
        'company_website':'https://www.stalexport-autostrady.pl' if ticker=='STX.WA' else None,
        'acquired_at':'2026-10-08T12:05:00+00:00','interval':'1h',
        'candle_status':'OPEN','candle_time':'2026-10-08T12:00:00Z',
        'candle_end':'2026-10-08T13:00:00Z','price':1.8,'indicators':{},'currency':'PLN'}


def item(date='2026-10-01T12:49:00Z',url='https://www.stalexport-autostrady.pl/raport'):
    return {'url':url,'title':'Raport nr 37/2026 - Otwarcie likwidacji VIA4 S.A.',
            'content':'Stalexport Autostrady S.A. informuje o otwarciu likwidacji spółki zależnej VIA4 S.A.',
            'published_date':date}


class TavilyStageCContractTests(unittest.TestCase):
    def test_01_plan_has_one_first_attempt_and_one_bounded_fallback(self):
        plan=KI.automatic_search_plan(snapshot())
        self.assertEqual([scope for scope,_ in plan],['fresh','fallback'])
        self.assertEqual(plan[0][1],KI.event_context_request({'snapshot':snapshot()}))
        self.assertEqual(plan[0][1]['include_domains_mode'],'restrict')
        self.assertEqual(plan[1][1]['include_domains_mode'],'prefer')
        self.assertEqual(plan[1][1]['query'],'Stalexport Autostrady')
        for _,request in plan:
            self.assertEqual(request['search_depth'],'basic')
            self.assertEqual(request['max_results'],5)
            self.assertEqual(request['start_date'],'2026-10-01')
            self.assertFalse(request['filter_by_published_date'])

    def test_02_fallback_search_plan_is_issuer_specific_no_sector_terms(self):
        for ticker,name in [('AAT.WA','Alta S.A.'),('3RG.WA','3R Games S.A.'),('HUMA','Humacyte, Inc.')]:
            with self.subTest(ticker=ticker):
                plan=KI.automatic_search_plan(snapshot(ticker,name))
                self.assertEqual(len(plan),2)
                self.assertNotIn('clinical',plan[1][1]['query'])
                self.assertNotIn('financing',plan[1][1]['query'])
                self.assertNotIn('180',plan[1][1]['start_date'])

    def test_03_empty_first_result_and_issuer_verified_fallback(self):
        s=snapshot();plan=KI.automatic_search_plan(s)
        result=KI.combine_automatic_tavily_results(s,[('fresh',plan[0][1],{'results':[]}),('fallback',plan[1][1],{'results':[item()], 'usage':{'credits':1}})])
        self.assertEqual(result['received_results'],1)
        self.assertEqual(len(result['sources']),1)
        self.assertEqual(result['sources'][0]['scope'],'fresh')
        self.assertEqual(result['sources'][0]['id'],'S1')
        self.assertEqual(len(result['attempts']),2)
        self.assertEqual(result['attempts'][0]['received_results'],0)
        self.assertEqual(result['attempts'][1]['accepted'],1)
        self.assertEqual(result['usage']['reported_credits'],1)
        self.assertEqual(result['usage']['reports_with_credits'],1)

    def test_04_two_attempts_deduplicate_sources(self):
        s=snapshot();plan=KI.automatic_search_plan(s)
        result=KI.combine_automatic_tavily_results(s,[('fresh',plan[0][1],{'results':[item()]}),('fallback',plan[1][1],{'results':[item()]})])
        self.assertEqual(len(result['sources']),1)
        self.assertEqual(result['duplicate_sources'],1)
        self.assertEqual(result['received_results'],2)

    def test_05_rejected_other_issuer_and_undated_cannot_reach_gpt(self):
        s=snapshot();plan=KI.automatic_search_plan(s)
        wrong={**item(), 'url':'https://unverified.example/other'}
        undated=item(date=None)
        result=KI.combine_automatic_tavily_results(s,[('fresh',plan[0][1],{'results':[wrong,undated]})])
        self.assertEqual(result['sources'],[])
        self.assertEqual(result['excluded'],2)
        request=KI.event_analysis_request({'snapshot':s},result)
        self.assertNotIn('unverified.example',request['messages'][-1]['content'])
        self.assertNotIn('VIA4 S.A.',request['messages'][-1]['content'])

    def test_06_missing_credit_field_is_unknown_not_zero(self):
        s=snapshot();p=KI.automatic_search_plan(s)
        r=KI.combine_automatic_tavily_results(s,[('fresh',p[0][1],{'results':[]})])
        self.assertIsNone(r['usage']['reported_credits'])
        self.assertEqual(r['usage']['reports_with_credits'],0)
        self.assertEqual(r['attempts'][0]['credits'],None)

    def test_07_diagnostics_are_excluded_from_openai_prompt(self):
        s=snapshot();plan=KI.automatic_search_plan(s)
        r=KI.combine_automatic_tavily_results(s,[('fresh',plan[0][1],{'results':[],'usage':{'credits':1}})])
        msg=KI.event_analysis_request({'snapshot':s},r)['messages'][-1]['content']
        self.assertNotIn('attempts',msg)
        self.assertNotIn('reported_credits',msg)
        self.assertNotIn('include_domains_mode',msg)

    def test_08_no_sources_is_an_explicit_diagnostic_not_no_news_claim(self):
        s=snapshot();p=KI.automatic_search_plan(s)
        r=KI.combine_automatic_tavily_results(s,[('fresh',p[0][1],{'results':[]}),('fallback',p[1][1],{'results':[]})])
        self.assertIn('pust',KI.tavily_result_summary(r))
        self.assertNotIn('Brak informacji',KI.tavily_result_summary(r))
        self.assertEqual(len(r['attempts']),2)
        self.assertEqual(r['sources'],[])


if __name__=='__main__': unittest.main(verbosity=2)
