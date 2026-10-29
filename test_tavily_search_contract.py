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
    def test_single_search_arguments_are_strict_and_absolute(self):
        import tavily_cli_adapter as adapter
        s=snap();r=adapter.build_search_arguments(KI.research_query(s,s['acquired_at']),8,**KI.event_search_arguments(s,s['acquired_at']))
        self.assertEqual(r['query'],'Stalexport Autostrady')
        self.assertEqual(r['search_depth'],'advanced')
        self.assertEqual(r['max_results'],8)
        self.assertTrue(r['filter_by_published_date'])
        self.assertEqual(r['include_domains_mode'],'restrict')

    def test_query_is_generic_for_polish_and_us_issuers(self):
        for ticker,name,expected in [('AAT.WA','Alta S.A.','Alta'),('3RG.WA','3R Games S.A.','3R Games'),('HUMA','Humacyte, Inc.','Humacyte')]:
            self.assertEqual(KI.research_query(snap(ticker,name),snap()['acquired_at']),expected)
        with self.assertRaises(ValueError):KI.research_query(snap(name=None),snap()['acquired_at'])

    def test_manual_and_automatic_dates_share_same_window(self):
        s=snap()
        self.assertEqual(KI.event_search_arguments(s,s['acquired_at']),KI.event_search_arguments({**s,'_manual_research':True},s['acquired_at']))

    def test_existing_quote_response_supplies_website_without_changing_spread(self):
        info={'symbol':'STX.WA','longName':'Stalexport Autostrady S.A.',
              'website':'https://www.stalexport-autostrady.pl','bid':1.80,'ask':1.82}
        quote=KI.quote_with_issuer_profile(info,'STX.WA')
        self.assertEqual(quote['spread_pct'],KI.spread_from_info(info)['spread_pct'])
        c={'ticker':'STX.WA','snapshot':snap()};original=copy.deepcopy(c['snapshot'])
        KI.attach_manual_quote(c,quote)
        self.assertEqual(c['snapshot']['company_website'],info['website'])
        self.assertEqual(original,snap())
        self.assertIn('stalexport-autostrady.pl',KI.event_search_arguments(c['snapshot'],c['snapshot']['acquired_at'])['include_domains'])
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
        self.assertIn('stalexport-autostrady.pl',KI.event_search_arguments(s,s['acquired_at'])['include_domains'])
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
        result=KI.normalize_tavily_context({'results':[source('2026-09-01T12:00:00Z')]},snap(website='https://stalexport-autostrady.pl'),180)
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

    def test_new_manual_turn_does_not_reuse_empty_previous_turn(self):
        with tempfile.TemporaryDirectory() as folder:
            store=KI.Store(Path(folder)/'test.sqlite')
            context={'ticker':'STX.WA','snapshot':snap(),'report_version':3,'research':{'status':'PENDING','sources':[]}}
            ids=[KI.begin_gpt_chat(store,'Co wiadomo?',context) for _ in range(2)]
            self.assertNotEqual(ids[0],ids[1])
            with store.connection() as c:
                self.assertEqual(c.execute('SELECT COUNT(*) FROM gpt_chat_turns').fetchone()[0],2)
                self.assertEqual(c.execute('SELECT COUNT(*) FROM analysis_jobs').fetchone()[0],0)

    def test_diagnostic_counts_survive_sqlite_without_jobs_or_delivery(self):
        with tempfile.TemporaryDirectory() as folder:
            store=KI.Store(Path(folder)/'test.sqlite');s=snap(website='https://stalexport-autostrady.pl')
            context={'ticker':s['ticker'],'snapshot':s,'report_version':3,'research':{'status':'PENDING','sources':[]}}
            turn=KI.begin_gpt_chat(store,'Co wiadomo?',context)
            context['research'].update(KI.r1_research_sources({'results':[source(None)]},s['acquired_at'],s))
            KI.save_gpt_chat_context(store,turn,context)
            with store.connection() as c:
                saved=json.loads(c.execute('SELECT context FROM gpt_chat_turns WHERE id=?',(turn,)).fetchone()[0])
                self.assertEqual(saved['research']['date_unverified_count'],1)
                self.assertEqual(saved['research']['sources'],[])
                self.assertEqual(c.execute('SELECT COUNT(*) FROM outbox').fetchone()[0],0)
                self.assertEqual(c.execute('SELECT COUNT(*) FROM analysis_jobs').fetchone()[0],0)

    def test_verified_date_changes_diagnostic_into_accepted_source(self):
        s=snap(website='https://stalexport-autostrady.pl')
        before=KI.r1_research_sources({'results':[source(None)]},s['acquired_at'],s)
        after=KI.r1_research_sources({'results':[source()]},s['acquired_at'],s)
        self.assertEqual(before['date_unverified_count'],1)
        self.assertEqual(before['sources'],[])
        self.assertEqual(after['undated_sources'],[])
        self.assertEqual(len(after['sources']),1)


if __name__=='__main__':unittest.main(verbosity=2)
