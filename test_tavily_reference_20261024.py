"""Kontrakty ustalone przez porównanie lokalnego Tavli i KI; bez API i mocków."""
import copy
import tempfile
import unittest
from pathlib import Path
import KI
import tavily_cli_adapter as adapter


class TavilyReferenceTests(unittest.TestCase):
    def snapshot(self):
        return {'ticker':'STX.WA','company_name':'Stalexport Autostrady S.A.',
                'company_website':'https://stalexport-autostrady.pl',
                'acquired_at':'2026-10-08T12:05:00+00:00','candle_status':'OPEN','indicators':{}}

    def source(self,date='2026-10-08T11:00:00Z'):
        return {'url':'https://stalexport-autostrady.pl/report',
                'title':'Stalexport Autostrady raport',
                'content':'Stalexport Autostrady opublikował raport.','published_date':date}

    def test_search_query_uses_only_verified_name(self):
        cases=[('GMT.WA','Genomtec S.A.','Genomtec'),
               ('MREO','Mereo BioPharma Group plc','Mereo BioPharma Group'),

               ('MIG.WA','MIG C.XNCO PLN','MIG')]
        for ticker,name,expected in cases:
            with self.subTest(ticker=ticker,name=name):
                snapshot={**self.snapshot(),'ticker':ticker,'company_name':name}
                self.assertEqual(KI.research_query(snapshot,snapshot['acquired_at']),expected)

    def test_short_query_does_not_remove_identity_or_date_validation(self):
        snapshot=self.snapshot();cutoff=snapshot['acquired_at']
        self.assertEqual(KI.research_query(snapshot,cutoff),'Stalexport Autostrady')
        context=KI.r1_research_sources({'request_id':'test','results':[self.source()]},cutoff,snapshot)
        self.assertEqual(context['issuer_identity']['ticker'],'STX.WA')
        self.assertEqual(context['cutoff'],cutoff)
        self.assertEqual(len(context['sources']),1)
        for date in (None,'2026-10-08T12:06:00Z'):
            self.assertEqual(KI.r1_research_sources({'results':[self.source(date)]},cutoff,snapshot)['sources'],[])

    def test_domain_restrictions_and_absolute_dates_reach_search_arguments(self):
        args=KI.event_search_arguments(self.snapshot(),self.snapshot()['acquired_at'])
        request=adapter.build_search_arguments('Stalexport STX.WA',8,**args)
        self.assertIn('stalexport-autostrady.pl',request['include_domains'])
        self.assertEqual(request['include_domains_mode'],'restrict')
        self.assertEqual(request['start_date'],'2026-09-08')
        self.assertEqual(request['end_date'],'2026-10-09')  # API: przed datą końcową; lokalny cutoff pozostaje dokładny
        self.assertNotIn('time_range',request)
        self.assertTrue(request['include_published_date'])
        self.assertTrue(request['filter_by_published_date'])

    def test_invalid_domain_configuration_never_falls_back_to_unrestricted_request(self):
        for domains in ([],['https://gpw.pl'],['gpw.pl/path'],['gpw.pl;other'], 'gpw.pl'):
            with self.subTest(domains=domains):
                with self.assertRaises(adapter.CLITransportError):
                    adapter.search_sync('query','not-a-real-key',include_domains=domains)

    def test_invalid_dates_are_rejected_before_network(self):
        for start,end in [('2026-10-09','2026-10-08'),('bad','2026-10-08')]:
            with self.assertRaises(adapter.CLITransportError):
                adapter.search_sync('query','not-a-real-key',start_date=start,end_date=end)

    def test_raw_response_and_real_id_and_usage_are_preserved_without_mutation(self):
        response={'request_id':'provider-123','results':[self.source()],
                  'usage':{'credits':2},'other':{'nested':['original']}}
        before=copy.deepcopy(response)
        normalized=adapter.normalize_search_response(response,adapter.build_search_arguments('STX.WA'))
        self.assertEqual(normalized['raw_response'],before)
        self.assertEqual(normalized['request_id'],'provider-123')
        self.assertEqual(normalized['usage'],{'credits':2})
        normalized['results'][0]['content']='changed'
        normalized['raw_response']['other']['nested'].append('copy')
        self.assertEqual(response,before)

    def test_full_source_text_is_preferred_without_losing_date_metadata(self):
        source={**self.source(),'raw_content':'Pełny tekst raportu emitenta.'}
        result=adapter.normalize_search_response({'results':[source]},adapter.build_search_arguments('STX.WA'))
        self.assertEqual(result['results'][0]['content'],source['raw_content'])
        self.assertEqual(result['results'][0]['content_origin'],'raw_content')
        self.assertEqual(result['results'][0]['published_date'],source['published_date'])

    def test_rejected_noise_remains_in_complete_provider_response(self):
        raw={'results':[{**self.source(),'url':'https://example.org/quote/STX'}]}
        result=adapter.normalize_search_response(raw,adapter.build_search_arguments('STX.WA'))
        self.assertEqual(result['results'],[])
        self.assertEqual(len(result['transport_rejections']),1)
        self.assertEqual(result['raw_response'],raw)

    def test_local_reservation_id_is_not_claimed_to_be_provider_id(self):
        result=KI.search_result_record({'request_id':None,'results':[]},'local-reservation')
        self.assertEqual(result['request_id'],'local-reservation')
        self.assertIsNone(result['provider_request_id'])
        self.assertEqual(result['request_id_origin'],'local_search_reservation')
        actual=KI.search_result_record({'request_id':'actual-123','results':[]},'local-reservation')
        self.assertEqual(actual['request_id'],'actual-123')
        self.assertEqual(actual['request_id_origin'],'provider_search')

    def test_undated_or_invalid_source_is_diagnostic_only(self):
        for date in (None,'','not a date'):
            context=KI.normalize_tavily_context({'results':[self.source(date)]},self.snapshot())
            self.assertEqual(context['sources'],[])
            self.assertEqual(context['date_unverified_count'],1)
            self.assertEqual(context['excluded'],1)
            request=KI.event_analysis_request({'snapshot':self.snapshot()},context)
            self.assertNotIn('Stalexport Autostrady opublikował raport.',request['messages'][-1]['content'])

    def test_date_and_issuer_restrictions_are_not_relaxed(self):
        for source in (self.source('2026-10-08T12:06:00Z'),self.source('2026-08-01T12:00:00Z'),
                       {**self.source(),'url':'https://unverified.example/report'},
                       {**self.source(),'title':'Other Issuer','content':'Other Issuer report.'}):
            self.assertEqual(KI.normalize_tavily_context({'results':[source]},self.snapshot(),30)['sources'],[])
        self.assertEqual(len(KI.normalize_tavily_context({'results':[self.source()]},self.snapshot(),30)['sources']),1)

    def test_saved_research_is_not_replaced_by_another_paid_search(self):
        with tempfile.TemporaryDirectory() as d:
            store=KI.Store(Path(d)/'manual.sqlite3')
            context={'ticker':'STX.WA','engine':'openai','research':{'status':'SUBMITTED','backend':'RESEARCH','request_id':'saved-provider-id'}}
            turn=KI.begin_gpt_chat(store,'Pytanie',context)
            before=copy.deepcopy(context)
            with self.assertRaises(KI.ServiceError):
                KI.collect_manual_research(store,turn,context,self.snapshot(),'not-a-real-key')
            self.assertEqual(context,before)
            with store.connection() as c:
                self.assertEqual(c.execute('SELECT state FROM gpt_chat_turns WHERE id=?',(turn,)).fetchone()[0],'REQUESTED')


if __name__=='__main__':unittest.main(verbosity=2)
