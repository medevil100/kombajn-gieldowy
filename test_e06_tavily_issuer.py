"""E06: testy kontraktow Tavily na jawnych danych, bez mockow i uslug sieciowych."""
import unittest
import KI


def snapshot(ticker='STX.WA', company='Stalexport Autostrady S.A.'):
    return {'ticker': ticker, 'company_name': company, 'company_website': None,
            'acquired_at': '2026-10-08T12:05:00Z', 'candle_status': 'OPEN',
            'candle_end': '2026-10-08T13:00:00Z', 'indicators': {}, 'currency': 'PLN'}


def result(url='https://gielda-przyklad.example/wiadomosci/stalexport',
           title='Stalexport Autostrady publikuje nowy raport',
           content='Stalexport Autostrady poinformowal o wynikach spolki.',
           published='2026-10-08T11:30:00Z'):
    return {'url': url, 'title': title, 'content': content, 'published_date': published}


class E06TavilyIssuerTests(unittest.TestCase):
    def test_01_only_fallback_can_accept_external_source_with_issuer_name_in_title_and_body(self):
        s=snapshot();plan=KI.automatic_search_plan(s)
        fresh=KI.combine_automatic_tavily_results(s,[('fresh',plan[0][1],{'results':[result()]})])
        self.assertEqual(fresh['sources'], [])
        fallback=KI.combine_automatic_tavily_results(s,[('fresh',plan[0][1],{'results':[]}),('fallback',plan[1][1],{'results':[result()]})])
        self.assertEqual(len(fallback['sources']),1)
        self.assertIn('zewnętrzn',fallback['sources'][0]['issuer_match'])
        self.assertEqual(fallback['attempts'][1]['accepted'],1)
        self.assertEqual(fallback['sources'][0]['scope'],'fresh')

    def test_02_external_source_requires_name_in_title_and_content(self):
        s=snapshot();p=KI.automatic_search_plan(s)[1][1]
        for case in [result(title='Raport giełdowy z dziś'),
                     result(content='Inny emitent opublikowal raport.'),
                     result(title='Raport: Stalexport Autostrady',content='Artykul o rynku. ' + 'X '*250+'Stalexport Autostrady'),
                     result(url='https://domain-example.test/news',title='Stalexport Autostrady raport',content='Inna spolka')]:
            with self.subTest(case=case):
                found=KI.combine_automatic_tavily_results(s,[('fallback',p,{'results':[case]})])
                self.assertEqual(found['sources'],[])

    def test_03_unknown_issuer_or_short_name_cannot_authorize_external_domain(self):
        for s in [snapshot('STX.WA',None),snapshot('AAT.WA','Alta S.A.')]:
            plan=KI.automatic_search_plan(s)[1][1]
            candidate=result(title=(s['company_name'] or 'STX.WA')+' raport',content=(s['company_name'] or 'STX.WA')+' potwierdzono')
            found=KI.combine_automatic_tavily_results(s,[('fallback',plan,{'results':[candidate]})])
            self.assertEqual(found['sources'],[])

    def test_04_outside_source_must_still_have_credible_date(self):
        s=snapshot();p=KI.automatic_search_plan(s)[1][1]
        for value in [None,'2026-10-08','2026-10-08T12:06:00Z','2026-09-28T10:00:00Z']:
            with self.subTest(date=value):
                found=KI.combine_automatic_tavily_results(s,[('fallback',p,{'results':[result(published=value)]})])
                self.assertEqual(found['sources'],[])

    def test_05_rejection_reasons_visible_per_attempt_but_not_to_gpt(self):
        s=snapshot();p=KI.automatic_search_plan(s)
        found=KI.combine_automatic_tavily_results(s,[('fresh',p[0][1],{'results':[]}),('fallback',p[1][1],{'results':[result(content='Not this company.'), result(published=None,url='https://elsewhere.example/report')]})])
        self.assertEqual(found['received_results'],2)
        self.assertEqual(found['attempts'][0]['received_results'],0)
        self.assertEqual(found['attempts'][1]['received_results'],2)
        self.assertEqual(found['attempts'][1]['accepted'],0)
        self.assertEqual(found['attempts'][1]['excluded'],2)
        self.assertTrue(found['attempts'][1]['rejection_reasons'])
        self.assertIn('odrzucone',KI.tavily_result_summary(found).lower())
        gpt=KI.event_analysis_request({'snapshot':s},found)['messages'][-1]['content']
        self.assertNotIn('rejection_reasons',gpt)

    def test_06_timestamps_are_saved_when_provided_without_change_to_existing_three_tuple_contract(self):
        s=snapshot();p=KI.automatic_search_plan(s)[0][1]
        a=KI.combine_automatic_tavily_results(s,[('fresh',p,{'results':[]},'2026-10-08T12:00:00Z','2026-10-08T12:00:01Z')])
        self.assertEqual(a['attempts'][0]['requested_at'],'2026-10-08T12:00:00Z')
        self.assertEqual(a['attempts'][0]['received_at'],'2026-10-08T12:00:01Z')
        b=KI.combine_automatic_tavily_results(s,[('fresh',p,{'results':[]})])
        self.assertIsNone(b['attempts'][0]['requested_at'])

    def test_07_external_source_never_laundered_into_primary_verified_domain(self):
        s=snapshot();r=result()
        normal=KI.normalize_tavily_context({'results':[r]},s)
        self.assertEqual(normal['sources'],[])
        fallback=KI.normalize_tavily_context({'results':[r]},s,allow_external_domains=True)
        self.assertEqual(len(fallback['sources']),1)
        self.assertEqual(fallback['sources'][0]['source_provenance'],'external')

    def test_08_unencrypted_external_source_is_rejected(self):
        s=snapshot();p=KI.automatic_search_plan(s)[1][1]
        found=KI.combine_automatic_tavily_results(s,[('fallback',p,{'results':[result(url='http://gielda-przyklad.example/story')]})])
        self.assertEqual(found['sources'],[])
        self.assertIn('HTTPS',found['attempts'][0]['rejection_reasons'].keys().__str__())

    def test_09_real_source_from_allowed_issuer_domain_keeps_old_qualification(self):
        s=snapshot();r=result(url='https://www.gpwinfostrefa.pl/news')
        original=KI.normalize_tavily_context({'results':[r]},s)
        fallback=KI.normalize_tavily_context({'results':[r]},s,allow_external_domains=True)
        self.assertEqual(len(original['sources']),1)
        self.assertEqual(len(fallback['sources']),1)
        self.assertEqual(original['sources'][0]['source_provenance'],'listed')
        self.assertEqual(original['sources'][0]['issuer_match'],fallback['sources'][0]['issuer_match'])

if __name__=='__main__': unittest.main(verbosity=2)
