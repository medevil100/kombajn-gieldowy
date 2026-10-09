import unittest
import tempfile
from pathlib import Path
import KI

class ResearchV3Tests(unittest.TestCase):
    def snapshot(self):
        return {'ticker':'HUMA','company_name':'Humacyte, Inc.','acquired_at':'2026-10-07T16:27:12+00:00','_manual_research':True}
    def test_identity_and_official_domain(self):
        identity=KI.issuer_search_identity(self.snapshot())
        self.assertEqual(identity['name'],'Humacyte')
        self.assertIn('humacyte.com',identity['domains'])
    def test_background_separate_from_fresh(self):
        snap=self.snapshot()
        source={'url':'https://investors.humacyte.com/news/example','title':'Humacyte announces board appointments','content':'Humacyte, Inc. announces board appointments.','published_date':'2026-09-28T12:00:00Z'}
        self.assertEqual(KI.normalize_tavily_context({'results':[source]},snap)['sources'],[])
        context=KI.normalize_tavily_context({'results':[source]},snap,window_days=180)
        self.assertEqual(len(context['sources']),1)
        self.assertEqual(context['sources'][0]['scope'],'background')
        source['published_date']='2026-10-08T12:00:00Z'
        self.assertEqual(KI.normalize_tavily_context({'results':[source]},snap,window_days=180)['sources'],[])
    def test_numbers_bound_to_fields(self):
        context={'ticker':'HUMA','report_version':3,'snapshot':{'price':.4659,'currency':'USD'},'research':{'sources':[]}}
        reply={'answer':'Cena wynosi {{metric:price}}.','metrics':['price'],'facts':[],'risks':[],'missing':[]}
        rendered=KI.render_manual_research_reply(reply,context)
        self.assertIn('0,4659 USD',rendered)
        reply['answer']='Cena wynosi {{metric:unknown}}.'
        with self.assertRaises(ValueError):KI.render_manual_research_reply(reply,context)
        reply['answer']='Cena wynosi 99 USD.'
        with self.assertRaises(ValueError):KI.render_manual_research_reply(reply,context)
    def test_background_cache_identity_and_expiry(self):
        with tempfile.TemporaryDirectory() as folder:
            store=KI.Store(Path(folder)/'test.sqlite')
            snap=self.snapshot()
            KI.save_issuer_background(store,snap,{'sources':[]},now='2026-10-07T16:00:00Z')
            self.assertIsNotNone(KI.load_issuer_background(store,snap,now='2026-10-07T17:00:00Z'))
            self.assertIsNone(KI.load_issuer_background(store,snap,now='2026-10-08T17:00:00Z'))
            self.assertIsNone(KI.load_issuer_background(store,{**snap,'ticker':'GOSS'},now='2026-10-07T17:00:00Z'))
    def test_manual_search_plan_bounded(self):
        plans=KI.manual_search_plan(self.snapshot())
        self.assertEqual([x[0] for x in plans],['fresh','fallback','background'])
        self.assertNotIn(',',plans[0][1]['query'])
        self.assertNotEqual(plans[0][1]['query'],plans[1][1]['query'])

    def test_mreo_alias_on_syndicated_domain_and_goss_identity(self):
        snap={**self.snapshot(),'ticker':'MREO','company_name':'Mereo BioPharma Group plc'}
        result={'url':'https://www.globenewswire.com/news-release/example','title':'Mereo BioPharma Reports Financial Results','content':'Mereo BioPharma Group plc (NASDAQ: MREO) reported financial results.'}
        self.assertTrue(KI.issuer_source_match(result,snap))
        with self.assertRaises(ValueError):
            KI.issuer_source_match({**result,'title':'Unrelated company report','content':'An unrelated company reported earnings.'},snap)
        goss=KI.issuer_search_identity({**self.snapshot(),'ticker':'GOSS','company_name':'Gossamer Bio, Inc.'})
        self.assertEqual(goss['name'],'Gossamer Bio')
        self.assertIn('gossamerbio.com',goss['domains'])
    def test_v3_request_and_legacy_automatic_search_isolation(self):
        snap=self.snapshot()
        legacy=KI.issuer_search_identity({k:v for k,v in snap.items() if k!='_manual_research'})
        self.assertNotIn('humacyte.com',legacy['domains'])
        self.assertEqual(KI.event_context_request({'snapshot':snap})['max_results'],5)
        context={'ticker':'HUMA','report_version':3,'snapshot':{'ticker':'HUMA','price':.4659,'currency':'USD','candle_status':'OPEN'},'research':{'sources':[]}}
        request=KI.gpt_chat_request('Co pokazują dane?',context,[])
        self.assertIn('{{metric:price}}',request['messages'][0]['content'])
        self.assertIn('nie potwierdza słabej aktywności',request['messages'][0]['content'])
        self.assertEqual(request['max_completion_tokens'],2600)

if __name__=='__main__':unittest.main()
