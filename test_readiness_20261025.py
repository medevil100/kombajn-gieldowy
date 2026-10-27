"""Regresje startu KI 2: prawdziwy SQLite i zapisane odpowiedzi, bez sieci."""
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
import KI
import tavily_cli_adapter as adapter
from test_repair_20261024 import NOW


class ReadinessTests(unittest.TestCase):
    def test_analysis_entrypoint_has_no_unresolved_global_names(self):
        import builtins
        import inspect
        import symtable
        scope=symtable.symtable(inspect.getsource(KI.analyze_event),'<analyze_event>','exec').get_children()[0]
        unresolved=[symbol.get_name() for symbol in scope.get_symbols()
                    if symbol.is_referenced() and symbol.is_global()
                    and symbol.get_name() not in vars(KI)
                    and not hasattr(builtins,symbol.get_name())]
        self.assertEqual(unresolved,[])
        self.assertTrue(scope.lookup('snap').is_local())

    def test_huma_saved_truncation_is_explicit_and_not_accepted(self):
        body={'choices':[{'finish_reason':'length','message':{'content':'{"answer":"urwany'}}],
              'usage':{'completion_tokens':2600}}
        with self.assertRaisesRegex(KI.ServiceError,'limit') as caught:
            KI.parse_gpt_chat_response(body)
        self.assertTrue(caught.exception.uncertain)
        self.assertFalse(caught.exception.retryable)

    def test_refusal_and_malformed_response_are_not_success(self):
        for body in ({'choices':[]},{'choices':[{'finish_reason':'stop','message':{'content':None,'refusal':'No'}}]}):
            with self.assertRaises(KI.ServiceError):KI.parse_gpt_chat_response(body)
        answer,_=KI.parse_gpt_chat_response({'choices':[{'finish_reason':'stop','message':{'content':'Pełny wynik'}}]})
        self.assertEqual(answer,'Pełny wynik')

    def test_full_report_has_bounded_larger_budget_same_model_and_schema(self):
        context={'ticker':'HUMA','report_version':3,'snapshot':{'ticker':'HUMA','price':.4153,'currency':'USD'},'research':{'sources':[]}}
        request=KI.gpt_chat_request('Co pokazują dane?',context,[])
        self.assertEqual(request['model'],'gpt-4o-mini')
        self.assertEqual(request['max_completion_tokens'],5000)
        self.assertTrue(request['response_format']['json_schema']['strict'])
        self.assertIn('Nie powtarzaj całego katalogu',request['messages'][0]['content'])

    def test_delivered_message_and_receipt_survive_finishing_again(self):
        with tempfile.TemporaryDirectory() as folder:
            store=KI.Store(Path(folder)/'test.sqlite3')
            snap=KI.opportunity_test_snapshot(NOW,ticker='STX.WA',price=1.3)
            snap['indicators']={'rsi':55.}
            context={'sources':[]}
            result={'technical':[{'metric':'rsi','interpretation':'RSI wynosi 55.'}],
                    'context':[],'hypotheses':[],'risks':[],'missing':[]}
            with store.transaction() as c:
                c.execute('INSERT INTO events VALUES(?,?,?,?,?)',('e','STX.WA','1h',NOW.isoformat(),KI.json_text({'snapshot':snap,'manual_analysis':True})))
                c.execute('INSERT INTO analysis_jobs(event_id,state,context,updated_at) VALUES(?,?,?,?)',('e','BUSY_AI',KI.json_text(context),NOW.isoformat()))
                c.execute('INSERT INTO outbox(id,event_id,kind,message,status,created_at) VALUES(?,?,?,?,?,?)',('e:analysis','e','ANALYSIS','Doręczony tekst','DELIVERED',NOW.isoformat()))
                c.execute('INSERT INTO delivery_receipts VALUES(?,?,?,?)',('e:analysis','local-test',123,NOW.isoformat()))
            KI.finish_analysis(store,'e',result,{'model':'test'},now=NOW)
            with store.connection() as c:
                self.assertEqual(tuple(c.execute('SELECT message,status FROM outbox').fetchone()),('Doręczony tekst','DELIVERED'))
                self.assertEqual(c.execute('SELECT message_id FROM delivery_receipts').fetchone()[0],123)
                self.assertEqual(c.execute('PRAGMA foreign_key_check').fetchall(),[])
                self.assertEqual(c.execute('SELECT state FROM analysis_jobs').fetchone()[0],'DONE')

    def test_claim_one_event_never_reserves_another(self):
        with tempfile.TemporaryDirectory() as folder:
            store=KI.Store(Path(folder)/'test.sqlite3')
            with store.transaction() as c:
                for eid in ('old','target'):
                    c.execute('INSERT INTO events VALUES(?,?,?,?,?)',(eid,'STX.WA','1h',NOW.isoformat(),json.dumps({'manual_analysis':True})))
                    c.execute('INSERT INTO analysis_jobs(event_id,state,updated_at) VALUES(?,?,?)',(eid,'PENDING_CONTEXT',NOW.isoformat()))
            self.assertEqual(KI.claim_analysis(store,'target',now=NOW)['event_id'],'target')
            self.assertIsNone(KI.claim_analysis(store,'target',now=NOW))
            with store.connection() as c:
                self.assertEqual(c.execute("SELECT state FROM analysis_jobs WHERE event_id='old'").fetchone()[0],'PENDING_CONTEXT')

    def test_extract_missing_key_is_observable_and_full_text_needs_no_extract(self):
        result=adapter.extract_urls(['https://example.org/report'],'')
        self.assertEqual(result,{})
        self.assertEqual(result.diagnostics['status'],'FAILED')
        response={'results':[{'url':'https://example.org/report','content':'Pełny tekst','content_origin':'raw_content'}]}
        adapter.enrich_search_response(response,'')
        self.assertEqual(response['extract_diagnostics']['status'],'NOT_NEEDED')
        self.assertEqual(response['results'][0]['content'],'Pełny tekst')

    def test_extract_diagnostics_preserved_in_research_not_gpt_prompt(self):
        snapshot={'ticker':'STX.WA','company_name':'Stalexport Autostrady','acquired_at':NOW.isoformat(),'indicators':{}}
        context=KI.r1_research_sources({'results':[],'extract_diagnostics':{'status':'FAILED','error':'EXTRACT_DIAGNOSTIC'}},NOW.isoformat(),snapshot)
        self.assertEqual(context['extract_diagnostics']['status'],'FAILED')
        request=KI.event_analysis_request({'snapshot':snapshot},context)
        self.assertNotIn('EXTRACT_DIAGNOSTIC',request['messages'][-1]['content'])

if __name__=='__main__':unittest.main()
