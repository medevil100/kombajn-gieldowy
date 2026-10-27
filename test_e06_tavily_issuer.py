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
    def context(self,values,s=None):
        s=s or snapshot()
        return KI.r1_research_sources({'results':values},s['acquired_at'],s)

    def test_external_domain_is_rejected_even_with_issuer_in_title_and_body(self):
        self.assertEqual(self.context([result()])['sources'],[])

    def test_portal_rejects_unrelated_issuer(self):
        for change in ({'title':'Inny emitent','content':'Inny emitent opublikował raport.'},):
            r=result(url='https://www.bankier.pl/report');r.update(change)
            self.assertEqual(self.context([r])['sources'],[])

    def test_unknown_identity_does_not_authorize_unknown_domain(self):
        for s in (snapshot('STX.WA',None),snapshot('AAT.WA','Alta S.A.')):
            self.assertEqual(self.context([result()],s)['sources'],[])

    def test_missing_future_and_old_dates_are_rejected(self):
        for date in (None,'bad','2026-10-08','2026-10-08T12:06:00Z','2026-09-01T10:00:00Z'):
            self.assertEqual(self.context([result(url='https://www.gpwinfostrefa.pl/report',published=date)])['sources'],[])

    def test_rejection_diagnostics_stay_outside_ai_prompt(self):
        s=snapshot();r=self.context([result(title='REJECTED_DIAGNOSTIC')],s)
        self.assertEqual(r['excluded'],1)
        self.assertTrue(r['rejected_sources'])
        self.assertNotIn('REJECTED_DIAGNOSTIC',KI.event_analysis_request({'snapshot':s},r)['messages'][-1]['content'])

    def test_allowed_source_retains_provenance_and_timestamp(self):
        r=self.context([result(url='https://www.gpwinfostrefa.pl/news')])
        self.assertEqual(len(r['sources']),1)
        self.assertEqual(r['sources'][0]['source_provenance'],'listed')
        self.assertEqual(r['sources'][0]['published_at'],'2026-10-08T11:30:00+00:00')

    def test_http_external_cannot_bypass_filter(self):
        self.assertEqual(self.context([result(url='http://outside.example/report')])['sources'],[])

    def test_domain_suffix_spoof_is_rejected(self):
        self.assertEqual(self.context([result(url='https://gpwinfostrefa.pl.evil.example/report')])['sources'],[])

if __name__=='__main__':unittest.main()
