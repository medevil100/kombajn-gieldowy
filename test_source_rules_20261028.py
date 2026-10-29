import copy
import unittest
import KI
import tavily_cli_adapter as adapter
import test_tavily_search_contract as fixture


class SourceRulesTests(unittest.TestCase):
    def test_no_query_without_confirmed_name(self):
        for ticker in ('XYZ','XYZ.WA'):
            with self.assertRaises(ValueError):KI.research_query(fixture.snap(ticker,name=None),fixture.snap()['acquired_at'])

    def test_date_without_hour_is_rejected_even_for_previous_day(self):
        for date in ('2026-10-07','2026-10-08'):
            ctx=KI.normalize_tavily_context({'results':[fixture.source(date)]},fixture.snap(website='https://stalexport-autostrady.pl'))
            self.assertEqual(ctx['sources'],[])
            self.assertIn('godziny',ctx['rejected_sources'][0]['reason'])

    def test_extract_oversized_batch_is_not_truncated_or_called(self):
        urls=['https://example.com/report/'+str(i) for i in range(9)]
        result=adapter.extract_urls(urls,'')
        self.assertEqual(result.diagnostics['status'],'LIMIT_EXCEEDED')
        self.assertEqual(result.diagnostics['attempted_count'],0)
        self.assertEqual(result.diagnostics['requested_count'],9)
        with self.assertRaises(KI.ServiceError):
            KI.r1_research_sources({'results':[],'extract_diagnostics':result.diagnostics},fixture.snap()['acquired_at'],fixture.snap())

    def test_identical_full_document_is_deduplicated_not_same_title(self):
        a={**fixture.source(),'content_origin':'raw_content'};b={**a,'url':a['url']+'/second'}
        before=copy.deepcopy([a,b]);results,rejected=adapter.deduplicate_results([a,b])
        self.assertEqual(len(results),1);self.assertEqual(len(rejected),1);self.assertEqual([a,b],before)
        b={**b,'content':a['content']+' Kolejny odrębny komunikat.'}
        self.assertEqual(len(adapter.deduplicate_results([a,b])[0]),2)

    def test_tracking_url_variants_prefer_full_document_over_snippet(self):
        a={**fixture.source(),'content_origin':'search_snippet'}
        b={**a,'url':a['url']+'?utm_source=test','content_origin':'raw_content','content':'Pełna treść komunikatu emitenta.'}
        results,rejected=adapter.deduplicate_results([a,b])
        self.assertEqual(len(results),1);self.assertEqual(results[0]['content_origin'],'raw_content')
        self.assertEqual(len(rejected),1)

    def test_pdf_is_not_rejected_just_for_being_pdf(self):
        s=fixture.snap(website='https://stalexport-autostrady.pl')
        result=fixture.source(url='https://stalexport-autostrady.pl/static-files/report.pdf')
        result['content_origin']='extract'
        self.assertEqual(len(KI.normalize_tavily_context({'results':[result]},s)['sources']),1)


if __name__=='__main__':unittest.main()
