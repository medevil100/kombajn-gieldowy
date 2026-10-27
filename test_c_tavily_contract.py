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
    def request(self,s=None):
        import tavily_cli_adapter as adapter
        s=s or snapshot()
        return adapter.build_search_arguments(KI.research_query(s,s['acquired_at']),8,**KI.event_search_arguments(s,s['acquired_at']))

    def test_single_search_uses_verified_name_strict_domains_and_month(self):
        r=self.request()
        self.assertEqual(r['query'],'Stalexport Autostrady')
        self.assertEqual(r['include_domains_mode'],'restrict')
        self.assertEqual(r['search_depth'],'advanced')
        self.assertEqual(r['max_results'],8)
        self.assertEqual(r['start_date'],'2026-09-08')
        self.assertEqual(r['end_date'],'2026-10-09')
        self.assertTrue(r['filter_by_published_date'])

    def test_queries_have_no_invented_sector_or_extra_fallback(self):
        for ticker,name in [('AAT.WA','Alta S.A.'),('3RG.WA','3R Games S.A.'),('HUMA','Humacyte, Inc.')]:
            r=self.request(snapshot(ticker,name))
            self.assertNotIn('clinical',r['query'])
            self.assertNotIn('financing',r['query'])
            self.assertNotIn('time_range',r)

    def test_one_response_is_filtered_and_deduplicated(self):
        s=snapshot();r=KI.r1_research_sources({'results':[item(),item()]},s['acquired_at'],s)
        self.assertEqual(len(r['sources']),1)
        self.assertEqual(r['excluded'],1)
        self.assertEqual(r['backend'],'SEARCH')

    def test_untrusted_undated_content_does_not_reach_gpt(self):
        s=snapshot();r=KI.r1_research_sources({'results':[item(None),item(url='https://unverified.example/other')]},s['acquired_at'],s)
        self.assertEqual(r['sources'],[])
        self.assertEqual(r['excluded'],2)
        prompt=KI.event_analysis_request({'snapshot':s},r)['messages'][-1]['content']
        self.assertNotIn('VIA4',prompt)
        self.assertNotIn('unverified.example',prompt)

    def test_provider_usage_and_raw_identity_are_preserved(self):
        import tavily_cli_adapter as adapter
        raw={'request_id':'provider-1','results':[item()],'usage':{'credits':2}}
        normalized=adapter.normalize_search_response(raw,self.request())
        r=KI.search_result_record(normalized,'local-fallback')
        self.assertEqual(r['provider_request_id'],'provider-1')
        self.assertEqual(r['usage'],{'credits':2})
        self.assertEqual(r['raw_response']['raw_response'],raw)

    def test_missing_usage_is_unknown(self):
        import tavily_cli_adapter as adapter
        r=adapter.normalize_search_response({'results':[]},self.request())
        self.assertIsNone(r['usage'])
        self.assertIsNone(r['request_id'])

    def test_empty_result_does_not_claim_absence_of_news(self):
        s=snapshot();r=KI.r1_research_sources({'results':[]},s['acquired_at'],s)
        self.assertIn('pust',KI.tavily_result_summary(r))
        self.assertIn('nie potwierdza braku',KI.tavily_result_summary(r))

if __name__=='__main__':unittest.main()
