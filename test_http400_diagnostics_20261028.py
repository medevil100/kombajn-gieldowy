import unittest
from provider_diagnostics import openai_error_detail
from ai_assessment import quote_candidates


class HttpDiagnosticTests(unittest.TestCase):
    def test_api_validation_error_has_code_parameter_and_redacted_message(self):
        body={'error':{'type':'invalid_request_error','code':'invalid_json_schema','param':'response_format',
                       'message':'Invalid schema. key=private-key-value https://private.example/token'},'private':'not included'}
        result=openai_error_detail(body,'private-key-value','req_123')
        self.assertIn('invalid_json_schema',result);self.assertIn('response_format',result)
        self.assertIn('Invalid schema',result);self.assertIn('req_123',result)
        self.assertNotIn('private-key-value',result);self.assertNotIn('private.example',result)
        self.assertNotIn('not included',result)

    def test_unknown_response_body_is_not_exposed(self):
        self.assertEqual(openai_error_detail({'untrusted':'secret'}),'')
        self.assertEqual(openai_error_detail('invalid JSON page with secrets'),'')
        self.assertLess(len(openai_error_detail({'error':{'message':'x'*10000}})),650)

    def test_issuer_filter_excludes_sidebars_and_broken_company_suffixes(self):
        content=('Image 4: Konsorcjum Torpolu ma ugodę z PKP PLK.\n'
                 'Nawet duża premia i atrakcyjne oprocentowanie nowego konta.\n'
                 'Zarząd One More Level S.\n'
                 'One More Level opublikował raport dotyczący sprzedaży gry.\n')
        result=quote_candidates({'content':content},['One More Level'])
        self.assertEqual(result,['One More Level opublikował raport dotyczący sprzedaży gry.'])

    def test_no_alias_means_no_automatic_quote_and_no_paraphrasing(self):
        source={'content':'Larq opublikował dzisiaj raport dotyczący wyników finansowych.'}
        self.assertEqual(quote_candidates(source,[]),[])
        result=quote_candidates(source,['LARQ'])
        self.assertEqual(result,[source['content']])
        self.assertIn(result[0],source['content'])


if __name__=='__main__':unittest.main()
