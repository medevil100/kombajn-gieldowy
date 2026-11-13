"""OpenAI web contract, budgets, citations and UI; only mocked HTTP."""
import json
import threading
import unittest
from unittest.mock import Mock, patch

import KI
import ki_assistant as a
import assistant_web as w
import test_ki_assistant_20261111 as fixtures
from test_ki_assistant_20261111 import reply, answer, REAL_HTTP


def web_reply():
    return {'status':'completed','usage':{'input_tokens':300,'output_tokens':100},'output':[
        {'type':'web_search_call','status':'completed','action':{'type':'search'}},
        {'type':'message','status':'completed','content':[{'type':'output_text',
          'text':'Emitent opublikował raport. [1]',
          'annotations':[{'type':'url_citation','start_index':27,'end_index':30,
                          'url':'https://example.org/report','title':'Raport emitenta'}]}]}]}


class WebTests(unittest.TestCase):
    setUp=fixtures.AssistantTests.setUp
    row=fixtures.AssistantTests.row
    turn=fixtures.AssistantTests.turn
    market_dump=fixtures.AssistantTests.market_dump

    def test_lookup_then_answer_uses_openai_only_and_preserves_market_data(self):
        turn=self.turn('Sprawdź w internecie najnowsze wiadomości Humacyte HUMA')
        before=self.market_dump()
        fake=Mock(side_effect=[reply('web_search',{'query':'Humacyte HUMA latest news'}),reply('answer',answer(['E1']))])
        with patch.object(KI,'service_http',return_value=web_reply()) as network:
            a.run(KI,self.path,turn,fake)
        self.assertEqual(self.row(turn)['state'],'DONE')
        self.assertEqual(network.call_count,1)
        args=network.call_args.args
        self.assertEqual(args[1],'https://api.openai.com/v1/responses')
        self.assertEqual(args[2],'fixture-not-real')
        self.assertEqual(args[3]['max_tool_calls'],1)
        self.assertEqual(args[3]['tools'],[{'type':'web_search','search_context_size':'low'}])
        self.assertFalse(args[3]['store'])
        self.assertNotIn('portfolio',args[3]['input'])
        self.assertEqual(a.usage(self.path)['calls'],3)
        self.assertGreater(a.usage(self.path)['micro_usd'],11000)
        self.assertEqual(before,self.market_dump())
        ev=json.loads(self.row(turn)['evidence'])
        self.assertEqual(ev[0]['data']['status'],'READY')
        self.assertIn('[Raport emitenta](https://example.org/report)',w.paragraph_links(answer(['E1'])['paragraphs'][0],ev))

    def test_real_http_adapter_accepts_responses_format(self):
        turn=self.turn()
        responses=[Mock(status_code=200,headers={},json=Mock(return_value=b)) for b in
                   [reply('web_search',{'query':'Humacyte HUMA news'}),web_reply(),reply('answer',answer(['E1']))]]
        with patch.object(KI,'service_http',REAL_HTTP),patch('requests.post',side_effect=responses) as post:
            a.run(KI,self.path,turn)
        self.assertEqual(self.row(turn)['state'],'DONE',self.row(turn))
        self.assertEqual([c.args[0] for c in post.call_args_list],
                         ['https://api.openai.com/v1/chat/completions','https://api.openai.com/v1/responses','https://api.openai.com/v1/chat/completions'])

    def test_ki_web_and_reviews_then_final_structured_answer(self):
        turn=self.turn()
        final={'choices':[{'finish_reason':'stop','message':{'content':json.dumps(answer(['E1','E2','E3']))}}],
               'usage':{'prompt_tokens':8160,'completion_tokens':472}}
        fake=Mock(side_effect=[reply('company',{'ticker':'HUMA'}),reply('web_search',{'query':'Humacyte HUMA latest news'}),reply('reviews',{'ticker':'HUMA'}),final])
        with patch.object(KI,'service_http',return_value=web_reply()) as network:
            a.run(KI,self.path,turn,fake)
        self.assertEqual(self.row(turn)['state'],'DONE',self.row(turn))
        self.assertEqual(fake.call_count,4);self.assertEqual(network.call_count,1)
        self.assertEqual(a.usage(self.path)['calls'],5)
        self.assertEqual([e['tool'] for e in json.loads(self.row(turn)['evidence'])],['company','web_search','reviews'])

    def test_search_repeat_and_reload_never_repeat_provider(self):
        turn=self.turn()
        with patch.object(KI,'service_http',return_value=web_reply()) as network:
            first=w.search(self.path,turn,KI,{'query':'HUMA news'})
            second=w.search(self.path,turn,KI,{'query':'HUMA different query'})
            a.ensure(self.path)
            third=w.search(self.path,turn,KI,{'query':'HUMA news'})
        self.assertEqual(first['status'],'READY');self.assertEqual(second['status'],'UNAVAILABLE')
        self.assertEqual(third['status'],'UNAVAILABLE');self.assertEqual(network.call_count,1)

    def test_timeout_preserves_reservation_and_can_still_answer_from_ki(self):
        turn=self.turn()
        fake=Mock(side_effect=[reply('web_search',{'query':'HUMA news'}),reply('company',{'ticker':'HUMA'}),reply('answer',answer(['E1','E2']))])
        with patch.object(KI,'service_http',side_effect=RuntimeError('sk-secret-do-not-store')) as network:
            a.run(KI,self.path,turn,fake)
        row=self.row(turn)
        self.assertEqual(row['state'],'DONE')
        self.assertNotIn('sk-secret',str(row));self.assertEqual(network.call_count,1)
        self.assertIn('UNAVAILABLE',row['evidence'])
        with a.database(self.path) as db:
            self.assertEqual(db.execute("SELECT c.state FROM assistant_calls c JOIN assistant_web_calls w ON w.call_id=c.id").fetchone()[0],'RESERVED')

    def test_budget_blocks_before_web_http(self):
        turn=self.turn()
        with patch.object(a,'DAILY_MICRO_USD',1),patch.object(KI,'service_http') as network:
            result=w.search(self.path,turn,KI,{'query':'HUMA news'})
        network.assert_not_called();self.assertEqual(result['status'],'UNAVAILABLE')

    def test_twenty_search_daily_cap_shared_between_threads(self):
        for index in range(20):
            thread=a.new_thread(self.path)
            turn=a.begin_turn(self.path,thread,'News')
            a.reserve(self.path,turn,{},web_query='public news '+str(index))
        turn=self.turn()
        with patch.object(KI,'service_http') as network:
            result=w.search(self.path,turn,KI,{'query':'HUMA news'})
        network.assert_not_called();self.assertIn('20',result['reason'])

    def test_one_search_reservation_is_atomic(self):
        turn=self.turn();results=[]
        def book():
            try:a.reserve(self.path,turn,{},web_query='HUMA news');results.append(True)
            except ValueError:results.append(False)
        workers=[threading.Thread(target=book) for _ in range(5)]
        for worker in workers:worker.start()
        for worker in workers:worker.join()
        self.assertEqual(results.count(True),1)

    def test_no_key_no_query_or_unbounded_input_does_not_call_provider(self):
        turn=self.turn()
        for args in ({'query':'a'*401},{'query':'sk-secret-value'},{'query':'news','url':'https://evil.test'},{'query':None}):
            with self.assertRaises(ValueError):w.search(self.path,turn,KI,args)
        with patch.object(KI,'load_service_keys',return_value={}),patch.object(KI,'service_http') as network:
            result=w.search(self.path,turn,KI,{'query':'HUMA news'})
        network.assert_not_called();self.assertEqual(result['status'],'UNAVAILABLE')

    def test_incomplete_uncited_and_unexecuted_results_are_not_claimed_ready(self):
        for alter in ('incomplete','no_web','no_citations','bad_span','unsafe_url','oversized'):
            body=web_reply()
            if alter=='incomplete':body['status']='incomplete'
            if alter=='no_web':body['output'].pop(0)
            part=body['output'][-1]['content'][0]
            if alter=='no_citations':part['annotations']=[]
            if alter=='bad_span':part['annotations'][0]['end_index']=10000
            if alter=='unsafe_url':part['annotations'][0]['url']='javascript:alert(1)'
            if alter=='oversized':part['text']='a'*3000
            self.assertNotEqual(w.parse(body)['status'],'READY',alter)

    def test_citations_are_clickable_and_malicious_links_rejected(self):
        result=w.parse(web_reply());text=w.cited_text(result['sections'][0])
        self.assertIn('Emitent opublikował raport.',text)
        self.assertIn('[Raport emitenta](https://example.org/report)',text)
        for url in ('file:///etc/passwd','http://localhost/','http://127.0.0.1/','http://169.254.169.254/','https://u:p@example.org/','https://example.org/?key=secret'):
            self.assertIsNone(w.public_url(url))
        self.assertNotIn('](javascript:',w.link('x](javascript:evil)','https://example.org/'))

    def test_ui_web_answer_sources_survive_refresh_without_network(self):
        from streamlit.testing.v1 import AppTest
        turn=self.turn()
        with patch.object(KI,'service_http',return_value=web_reply()):
            a.run(KI,self.path,turn,Mock(side_effect=[reply('web_search',{'query':'HUMA news'}),reply('answer',answer(['E1']))]))
        script='import KI, ki_assistant\nfrom pathlib import Path\nki_assistant.render(KI,ki_assistant.ReadStore(Path('+repr(str(self.path))+')))'
        app=AppTest.from_string(script).run(timeout=20)
        self.assertFalse(app.exception)
        self.assertTrue(any('[Raport emitenta](https://example.org/report)' in m.value for m in app.markdown))
        app.run();self.assertFalse(app.exception)


if __name__=='__main__':unittest.main()
