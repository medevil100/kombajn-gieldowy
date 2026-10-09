"""Jawne przypadki kontraktu Tavily i rzeczywiste SQLite; bez API i mocków."""
import copy
import json
import tempfile
from pathlib import Path
import unittest
import KI


def snap(ticker='STX.WA', name='Stalexport Autostrady S.A.', website=None):
    return {'ticker':ticker,'company_name':name,'company_website':website,
            'acquired_at':'2026-10-08T12:05:00+00:00','interval':'1h','candle_status':'OPEN',
            'candle_time':'2026-10-08T12:00:00Z','candle_end':'2026-10-08T13:00:00Z',
            'price':1.8,'indicators':{},'currency':'PLN'}


def source(date='2026-10-01T12:49:00Z', url='https://www.stalexport-autostrady.pl/raport'):
    # Jawny przypadek parsera, nie zapis odpowiedzi płatnego Tavily.
    return {'url':url,'title':'Raport nr 37/2026 - Otwarcie likwidacji VIA4 S.A.',
            'content':'Stalexport Autostrady S.A. informuje o otwarciu likwidacji spółki zależnej VIA4 S.A.',
            'published_date':date}


class TavilySearchContractTests(unittest.TestCase):
    def test_polish_plan_has_local_terms_simple_fallback_and_no_sector_bias(self):
        plans=dict(KI.manual_search_plan(snap()))
        self.assertEqual(set(plans),{'fresh','fallback','background'})
        self.assertIn('raport',plans['fresh']['query'])
        self.assertEqual(plans['fallback']['query'],'Stalexport Autostrady')
        for request in plans.values():
            self.assertNotIn('STX.WA',request['query'])
            for term in ('clinical','financing','news press'):self.assertNotIn(term,request['query'])
            self.assertEqual(request['language'],'pl')
            self.assertFalse(request['exact_match'])
            self.assertFalse(request['filter_by_published_date'])
            self.assertTrue(request['include_published_date'])
            self.assertEqual(request['max_results'],5)
            self.assertEqual(request['search_depth'],'basic')
            self.assertFalse(request['auto_parameters'])
        self.assertEqual(plans['fallback']['include_domains_mode'],'prefer')
        self.assertEqual(plans['fresh']['start_date'],'2026-10-01')
        self.assertEqual(plans['background']['start_date'],'2026-04-11')

    def test_plan_is_generic_for_polish_and_us_issuers(self):
        for ticker,name in [('AAT.WA','Alta S.A.'),('3RG.WA','3R Games S.A.'),('HUMA','Humacyte, Inc.'),('XYZ','Other Holdings Inc.')]:
            with self.subTest(ticker=ticker):
                plans=KI.manual_search_plan(snap(ticker,name))
                for _,r in plans:
                    self.assertEqual(r['language'],'pl' if ticker.endswith('.WA') else 'en')
                    self.assertNotIn('clinical',r['query']);self.assertNotIn(ticker,r['query'])
        self.assertIn('STX.WA',KI.manual_search_plan(snap(name=None))[0][1]['query'])

    def test_automatic_request_uses_same_search_rules_without_extra_calls(self):
        r=KI.event_context_request({'snapshot':snap()})
        self.assertNotIn('STX.WA',r['query']);self.assertFalse(r['filter_by_published_date'])
        self.assertEqual(r['language'],'pl');self.assertEqual(r['max_results'],5)

    def test_existing_quote_response_supplies_website_without_changing_spread(self):
        info={'symbol':'STX.WA','longName':'Stalexport Autostrady S.A.',
              'website':'https://www.stalexport-autostrady.pl','bid':1.80,'ask':1.82}
        quote=KI.quote_with_issuer_profile(info,'STX.WA')
        self.assertEqual(quote['spread_pct'],KI.spread_from_info(info)['spread_pct'])
        c={'ticker':'STX.WA','snapshot':snap()};original=copy.deepcopy(c['snapshot'])
        KI.attach_manual_quote(c,quote)
        self.assertEqual(c['snapshot']['company_website'],info['website'])
        self.assertEqual(original,snap())
        self.assertIn('stalexport-autostrady.pl',KI.manual_search_plan(c['snapshot'])[0][1]['include_domains'])
        # Automatic opportunity snapshots retain the same quote object.
        identity=KI.issuer_search_identity({**snap(),'spread':quote})
        self.assertEqual(identity['issuer_domain'],'stalexport-autostrady.pl')

    def test_profile_of_other_ticker_or_name_cannot_authorize_domain(self):
        for info in ({'symbol':'OTHER','longName':'Stalexport Autostrady S.A.'},
                     {'symbol':'STX.WA','longName':'Other Issuer'},
                     {'longName':'Stalexport Autostrady S.A.'}):
            quote=KI.quote_with_issuer_profile({**info,'website':'https://foreign.example'},'STX.WA')
            c={'ticker':'STX.WA','snapshot':snap()};KI.attach_manual_quote(c,quote)
            self.assertNotIn('foreign.example',KI.issuer_search_identity(c['snapshot'])['domains'])

    def test_known_website_and_missing_website_are_explicit(self):
        s=snap(website='https://www.stalexport-autostrady.pl')
        self.assertIn('stalexport-autostrady.pl',KI.event_context_request({'snapshot':s})['include_domains'])
        for website in ('javascript:bad','https://user:password@example.org','https://localhost','https://127.0.0.1','not a URL'):
            self.assertIsNone(KI.issuer_search_identity(snap(website=website))['issuer_domain'])

    def test_verified_issuer_report_is_accepted_in_date_window(self):
        result=KI.normalize_tavily_context({'results':[source()]},snap(website='https://stalexport-autostrady.pl'))
        self.assertEqual(len(result['sources']),1);self.assertEqual(result['sources'][0]['scope'],'fresh')
        self.assertEqual(result['received_results'],1)

    def test_numbered_report_on_trusted_portal_still_requires_issuer_at_start(self):
        src=source(url='https://www.bankier.pl/report')
        result=KI.normalize_tavily_context({'results':[src]},snap())
        self.assertEqual(len(result['sources']),1)
        src['content']='Other Issuer report. '+('other text '*60)+src['content']
        self.assertEqual(KI.normalize_tavily_context({'results':[src]},snap())['sources'],[])

    def test_undated_matching_source_is_diagnostic_only(self):
        result=KI.normalize_tavily_context({'results':[source(None)]},snap(website='https://stalexport-autostrady.pl'))
        self.assertEqual(result['sources'],[]);self.assertEqual(result['excluded'],1)
        self.assertEqual(result['date_unverified_count'],1)
        self.assertEqual(result['undated_sources'][0]['url'],source()['url'])
        self.assertIn('dat',KI.tavily_result_summary(result))

    def test_invalid_date_and_same_day_without_time_stay_unverified(self):
        for date in ('bad date','2026-10-08','2026-10-08T10:00:00'):
            with self.subTest(date=date):
                result=KI.normalize_tavily_context({'results':[source(date)]},snap(website='https://stalexport-autostrady.pl'))
                self.assertEqual(result['sources'],[]);self.assertEqual(result['date_unverified_count'],1)

    def test_future_and_old_dates_cannot_become_fresh(self):
        for date in ('2026-10-08T12:06:00Z','2026-09-01T12:00:00Z'):
            result=KI.normalize_tavily_context({'results':[source(date)]},snap(website='https://stalexport-autostrady.pl'))
            self.assertEqual(result['sources'],[]);self.assertEqual(result['date_unverified_count'],0)
        result=KI.normalize_tavily_context({'results':[source('2026-09-01')]},snap(website='https://stalexport-autostrady.pl'),180)
        self.assertEqual(result['sources'][0]['scope'],'background')

    def test_preferred_domains_do_not_allow_unverified_sites_or_wrong_issuers(self):
        for change in ({'url':'https://stalexport-autostrady.pl.evil.example/report'},
                       {'url':'https://unknown.example/report'},
                       {'content':'Other Issuer announces financial results.'}):
            result=KI.normalize_tavily_context({'results':[{**source(None),**change}]},snap(website='https://stalexport-autostrady.pl'))
            self.assertEqual(result['sources'],[]);self.assertEqual(result['undated_sources'],[])

    def test_empty_results_not_confused_with_missing_dates(self):
        empty=KI.normalize_tavily_context({'results':[]},snap())
        self.assertIn('pust',KI.tavily_result_summary(empty))
        self.assertNotIn('Brak trafnych informacji',KI.tavily_result_summary(empty))
        self.assertIn('nie potwierdza braku',KI.tavily_result_summary(empty))
        with self.assertRaises(KI.ServiceError):KI.normalize_tavily_context({'error':'bad'},snap())

    def test_unverified_source_text_cannot_reach_gpt_or_be_cited(self):
        s=snap(website='https://stalexport-autostrady.pl')
        research=KI.normalize_tavily_context({'results':[source(None)]},s)
        research['undated_sources'][0]['title']='SECRET_UNVERIFIED_SOURCE_TEXT'
        c={'ticker':'STX.WA','report_version':3,'snapshot':s,'research':research}
        request=KI.gpt_chat_request('Co wiadomo?',c,[])
        self.assertNotIn('SECRET_UNVERIFIED_SOURCE_TEXT',request['messages'][-1]['content'])
        event=KI.event_analysis_request({'snapshot':s},research)
        self.assertNotIn('SECRET_UNVERIFIED_SOURCE_TEXT',event['messages'][-1]['content'])
        self.assertEqual(KI.manual_research_schema(c)['properties']['facts']['items']['properties']['source_id']['enum'],['UNAVAILABLE'])

    def test_old_empty_cache_does_not_suppress_new_search_policy(self):
        with tempfile.TemporaryDirectory() as folder:
            store=KI.Store(Path(folder)/'test.sqlite');s=snap()
            identity=KI.issuer_search_identity({**s,'_manual_research':True})
            oldkey=KI.json_text({'ticker':identity['ticker'],'name':identity['name'],'domains':identity['domains'],'version':3})
            KI.save_issuer_background(store,s,{'sources':[]},now=s['acquired_at'])
            with store.transaction() as con:
                con.execute('UPDATE manual_issuer_context SET identity=?',(oldkey,))
            self.assertIsNone(KI.load_issuer_background(store,s,now=s['acquired_at']))

    def test_diagnostic_counts_survive_sqlite_without_jobs_or_delivery(self):
        with tempfile.TemporaryDirectory() as folder:
            store=KI.Store(Path(folder)/'test.sqlite');s=snap(website='https://stalexport-autostrady.pl')
            c={'ticker':s['ticker'],'snapshot':s,'report_version':3,'research':{'sources':[],'excluded':0,'rejected_sources':[],
                 'undated_sources':[],'date_unverified_count':0}}
            turn=KI.begin_gpt_chat(store,'Co wiadomo?',c)
            n=KI.normalize_tavily_context({'results':[source(None)]},s)
            KI.merge_manual_research_result(store,turn,c,n)
            with store.connection() as con:
                saved=json.loads(con.execute('SELECT context FROM gpt_chat_turns WHERE id=?',(turn,)).fetchone()[0])
                self.assertEqual(saved['research']['date_unverified_count'],1)
                self.assertEqual(saved['research']['sources'],[])
                self.assertEqual(con.execute('SELECT COUNT(*) FROM outbox').fetchone()[0],0)
                self.assertEqual(con.execute('SELECT COUNT(*) FROM analysis_jobs').fetchone()[0],0)

    def test_later_verified_date_removes_url_from_unverified_list(self):
        with tempfile.TemporaryDirectory() as folder:
            store=KI.Store(Path(folder)/'test.sqlite');s=snap(website='https://stalexport-autostrady.pl')
            c={'ticker':s['ticker'],'snapshot':s,'report_version':3,'research':{'sources':[],'excluded':0,'rejected_sources':[]}}
            turn=KI.begin_gpt_chat(store,'Co wiadomo?',c)
            for item in (source(None),source()):
                KI.merge_manual_research_result(store,turn,c,KI.normalize_tavily_context({'results':[item]},s))
            self.assertEqual(len(c['research']['sources']),1)
            self.assertEqual(c['research']['undated_sources'],[])
            KI.save_issuer_background(store,s,{'sources':[], 'undated_sources':[{'url':source()['url'],'title':'Zapis diagnostyczny','reason':'Brak daty'}]},now=s['acquired_at'])
            cached=KI.load_issuer_background(store,s,now=s['acquired_at'])
            self.assertEqual(len(cached['undated_sources']),1)


if __name__=='__main__':unittest.main(verbosity=2)
