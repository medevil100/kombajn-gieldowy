import unittest

import KI


class IssuerPageDateTests(unittest.TestCase):
    def test_reads_article_publication_metadata(self):
        html = '<html><head><meta property="article:published_time" content="2026-10-01T14:49:00+02:00"></head></html>'
        result = KI.issuer_page_publication_date(html)
        self.assertEqual(result['value'], '2026-10-01T14:49:00+02:00')

    def test_reads_structured_data_and_time_tag(self):
        structured = '<script type="application/ld+json">{"@type":"NewsArticle","datePublished":"2026-10-01"}</script>'
        self.assertEqual(KI.issuer_page_publication_date(structured)['value'], '2026-10-01')
        time_tag = '<time datetime="2026-10-01T14:49:00Z">1 października</time>'
        self.assertEqual(KI.issuer_page_publication_date(time_tag)['value'], '2026-10-01T14:49:00Z')

    def test_ignores_pages_without_publication_metadata(self):
        self.assertIsNone(KI.issuer_page_publication_date('<html><body>Aktualności spółki</body></html>'))

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
