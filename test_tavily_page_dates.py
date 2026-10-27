import unittest

import KI


class IssuerPageDateTests(unittest.TestCase):
    def test_missing_provider_date_is_not_inferred_from_article_text(self):
        self.check_date(None,False)

    def test_invalid_and_unzoned_metadata_cannot_prove_publication(self):
        for value in ('bad','2026-10-01T14:49:00'):
            self.check_date(value,False)

    def check_date(self,value,accepted):
        s={'ticker':'STX.WA','company_name':'Stalexport Autostrady','company_website':'https://stalexport-autostrady.pl','acquired_at':'2026-10-08T13:00:00Z'}
        raw={'url':'https://stalexport-autostrady.pl/report','title':'Stalexport Autostrady raport','content':'Stalexport Autostrady opublikował raport.','published_date':value}
        self.assertEqual(bool(KI.r1_research_sources({'results':[raw]},s['acquired_at'],s)['sources']),accepted)

    def test_future_metadata_is_rejected(self):
        self.check_date('2026-10-08T13:00:01Z',False)

    def test_direct_page_date_is_accepted_by_existing_date_window_rules(self):
        snapshot = {'ticker': 'STX.WA', 'company_name': 'Stalexport Autostrady S.A.',
                    'company_website': 'https://stalexport-autostrady.pl',
                    'acquired_at': '2026-10-08T15:00:00+02:00'}
        payload = {'results': [{'url': 'https://stalexport-autostrady.pl/report/37',
                                'title': 'Raport nr 37/2026 - Stalexport Autostrady S.A.',
                                'content': 'Stalexport Autostrady S.A. informuje o raporcie.',
                                'published_date': '2026-10-01T14:49:00+02:00',
                                'published_date_source': 'official_page_metadata'}]}
        normalized = KI.normalize_tavily_context(payload, snapshot)
        self.assertEqual(len(normalized['sources']), 1)
        self.assertEqual(normalized['sources'][0]['published_date_source'], 'official_page_metadata')


if __name__ == '__main__':
    unittest.main()
