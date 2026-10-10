"""Kontrakt offline wariantów REST/CLI, bez fikcyjnych danych rynkowych i mocków."""
import unittest
import KI
import tavily_cli_adapter as cli


class TavilyCLIDualContract(unittest.TestCase):
    def test_rest_remains_default(self):
        self.assertEqual(KI.service_config({})['tavily_mode'], 'REST')

    def test_cli_is_explicit_switch(self):
        self.assertEqual(KI.service_config({'tavily_mode':'CLI'})['tavily_mode'], 'CLI')

    def test_unknown_backend_refused(self):
        with self.assertRaises(ValueError):
            KI.service_config({'tavily_mode':'INNY'})

    def test_cli_refuses_keyless(self):
        with self.assertRaises(cli.CLITransportError):
            cli._launch(['search', 'HUMA'], '')

    def test_no_local_source_censorship_is_passed_to_cli(self):
        args=cli._search_arguments({'query':'HUMA','max_results':5,'topic':'general',
                                    'include_domains':['sec.gov'],'include_domains_mode':'restrict'})
        self.assertEqual(args[0],'search')
        self.assertNotIn('--include-domains',args)
        self.assertNotIn('--include-domains-mode',args)
        self.assertNotIn('--include-published-date',args)

    def test_extract_rejects_private_and_non_https_urls(self):
        self.assertFalse(cli._safe_url('https://127.0.0.1/secret'))
        self.assertFalse(cli._safe_url('http://example.org/'))
        self.assertFalse(cli._safe_url('https://localhost/'))
        self.assertTrue(cli._safe_url('https://www.sec.gov/'))

    def test_missing_publication_date_remains_missing(self):
        self.assertEqual(cli._date(None), ('Brak daty','MISSING'))


if __name__=='__main__':
    unittest.main()
