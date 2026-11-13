"""Temporary SQLite, simulated tool calls and real Streamlit UI; no providers."""
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

import KI
import ki_assistant as a
REAL_HTTP=KI.service_http


def reply(name, args, usage=True):
    r={'choices':[{'finish_reason':'tool_calls','message':{'role':'assistant','content':None,
       'tool_calls':[{'id':'call_'+name,'type':'function','function':{'name':name,'arguments':json.dumps(args)}}]}}]}
    if usage:
        r['usage']={'prompt_tokens':1000,'completion_tokens':100}
    return r


def answer(ids=None):
    return {'paragraphs':[{'text':'Odczyt wskazuje wzrost; dalszy kierunek wymaga obserwacji.',
                           'evidence_ids':ids or []}], 'limitations':['To zapis danych, nie nowe notowanie.']}


class AssistantTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
        self.path=Path(tmp.name)/'fixture.sqlite3';self.store=KI.Store(self.path)
        a.ensure(self.path);self.thread=a.new_thread(self.path)
        self.at=a.now()
        self.enterContext(patch.object(KI,'load_service_keys',return_value={'OPENAI_API_KEY':'fixture-not-real'}))
        self.enterContext(patch.object(KI,'service_http',side_effect=AssertionError('No network')))
        self.enterContext(patch.object(KI,'fetch_market',side_effect=AssertionError('No Yahoo')))
        with self.store.connection() as db:
            snap={'ticker':'HUMA','interval':'1h','price':1.4,'currency':'USD','acquired_at':self.at,
                  'candle_status':'OPEN','price_matrix':{'change_pct':2.4},'indicators':{'rsi':45},
                  'raw_response':{'secret':'must-not-leak'},'chart_history':['large']*500}
            db.execute('INSERT INTO observations(ticker,interval,candle_time,acquired_at,candle_status,payload) VALUES(?,?,?,?,?,?)',
                       ('HUMA','1h',self.at,self.at,'OPEN',json.dumps(snap)))
            db.execute('INSERT INTO price_matrix VALUES(?,?,?)',('HUMA',json.dumps(snap['price_matrix']),self.at))
            db.execute('INSERT INTO runtime VALUES(?,?,?)',('orchestrator:HUMA',json.dumps({'action':'WAIT_FOR_ACTIVITY','reason':'MOVEMENT_NOT_READY'}),self.at))
            db.execute('INSERT INTO portfolio VALUES(?,?,?,?,?)',('HUMA',10,1.3,'USD','{}'))

    def row(self,turn):
        with a.database(self.path) as db:
            return dict(db.execute('SELECT * FROM assistant_turns WHERE id=?',(turn,)).fetchone())

    def turn(self,question='Dlaczego HUMA nie jest w TOP 5?'):
        return a.begin_turn(self.path,self.thread,question)

    def market_dump(self):
        with a.database(self.path) as db:
            names=[r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'") if not r[0].startswith('assistant_')]
            return {n:[tuple(r) for r in db.execute('SELECT * FROM '+n)] for n in names}

    def test_tools_are_read_only_and_omit_provider_payloads(self):
        before=self.market_dump();reader=a.Reader(self.path,KI)
        for name in a.READERS:
            args={'ticker':'HUMA'} if name in ('company','reviews','saved_news','daily_history') else {}
            if name=='daily_history':args['days']=364
            result=reader.run(name,args)
            self.assertNotIn('must-not-leak',str(result));self.assertNotIn('chart_history',str(result))
        self.assertEqual(before,self.market_dump())
        with a.database(self.path) as db:
            with self.assertRaises(sqlite3.OperationalError):
                db.execute('DELETE FROM portfolio')

    def test_real_read_then_answer_records_evidence_and_usage(self):
        turn=self.turn();before=self.market_dump()
        fake=Mock(side_effect=[reply('company',{'ticker':'HUMA'}),reply('answer',answer(['E1']))])
        a.run(KI,self.path,turn,fake)
        row=self.row(turn);self.assertEqual(row['state'],'DONE',row)
        evidence=json.loads(row['evidence']);self.assertEqual(evidence[0]['data']['orchestrator']['data']['action'],'WAIT_FOR_ACTIVITY')
        self.assertEqual(fake.call_count,2);self.assertEqual(a.usage(self.path)['calls'],2)
        self.assertEqual(a.usage(self.path)['micro_usd'],420)
        self.assertEqual(before,self.market_dump())
        self.assertTrue(fake.call_args.kwargs['uncertain'])

    def test_followup_has_memory_but_other_thread_does_not(self):
        turn=self.turn();a.run(KI,self.path,turn,Mock(return_value=reply('answer',answer())))
        follow=self.turn('A co z wolumenem?')
        fake=Mock(side_effect=[reply('company',{'ticker':'HUMA'}),reply('answer',answer(['E1']))])
        a.run(KI,self.path,follow,fake)
        messages=fake.call_args_list[0].args[3]['messages']
        self.assertTrue(any(m.get('content')=='Dlaczego HUMA nie jest w TOP 5?' for m in messages))
        other=a.new_thread(self.path)
        self.assertEqual(a.history(self.path,other,'absent'),[])

    def test_double_submission_and_running_lock(self):
        turn=a.begin_turn(self.path,self.thread,'HUMA',ident='same')
        self.assertEqual(a.begin_turn(self.path,self.thread,'HUMA',ident='same'),turn)
        with self.assertRaises(ValueError):self.turn()

    def test_missing_key_no_calls(self):
        turn=self.turn();fake=Mock()
        with patch.object(KI,'load_service_keys',return_value={}):a.run(KI,self.path,turn,fake)
        fake.assert_not_called();self.assertEqual(a.usage(self.path)['calls'],0)
        self.assertEqual(self.row(turn)['state'],'FAILED')

    def test_unknown_function_or_sql_ticker_never_executes(self):
        reader=a.Reader(self.path,KI)
        for name,args in [('shell',{'cmd':'pwd'}),('company',{'ticker':"HUMA'; DELETE FROM portfolio;--"}),
                          ('company',{'ticker':'HUMA','sql':'DELETE'}),('daily_history',{'ticker':'HUMA','days':999})]:
            with self.assertRaises(ValueError):reader.run(name,args)
        self.assertEqual(len(self.market_dump()['portfolio']),1)

    def test_unknown_evidence_is_rejected(self):
        turn=self.turn();fake=Mock(return_value=reply('answer',answer(['E999'])))
        a.run(KI,self.path,turn,fake)
        self.assertEqual(self.row(turn)['state'],'FAILED');self.assertEqual(fake.call_count,1)

    def test_response_truncated_refused_or_malformed_no_retry(self):
        for body in ({'choices':[{'finish_reason':'length','message':{}}]}, {'choices':[]},
                     {'choices':[{'finish_reason':'stop','message':{'refusal':'No'}}]}):
            turn=self.turn();fake=Mock(return_value=body);a.run(KI,self.path,turn,fake)
            self.assertEqual(self.row(turn)['state'],'FAILED');self.assertEqual(fake.call_count,1)

    def test_protocol_diagnostics_do_not_save_content_or_arguments(self):
        body=reply('company',{'ticker':'HUMA','secret':'do-not-save'})
        body['choices'][0]['message']['content']='private answer'
        body['choices'][0]['finish_reason']='length'
        turn=self.turn();fake=Mock(return_value=body)
        a.run(KI,self.path,turn,fake)
        with a.database(self.path) as db:
            diagnostic=db.execute('SELECT payload FROM assistant_call_diagnostics').fetchone()[0]
        self.assertNotIn('private',diagnostic);self.assertNotIn('do-not-save',diagnostic)
        self.assertEqual(json.loads(diagnostic)['finish_reason'],'length')
        self.assertIn('ucięta',self.row(turn)['error'])
        self.assertEqual(json.loads(self.row(turn)['evidence']),[])
        self.assertEqual(fake.call_count,1)

    def test_diagnostics_distinguish_stop_refusal_and_malformed_choices(self):
        for body,word in (({'choices':[{'finish_reason':'stop','message':{'content':'text'}}]},'formatu'),
                          ({'choices':[{'finish_reason':'stop','message':{'refusal':'private refusal'}}]},'odmówił'),
                          ({'choices':[]},'jednej'),({'choices':[None]},'struktura')):
            with self.assertRaisesRegex(ValueError,word):a.response_message(body)

    def test_network_uncertain_retains_budget_no_secret_in_error(self):
        turn=self.turn();fake=Mock(side_effect=RuntimeError('secret token sk-never-show-this'))
        a.run(KI,self.path,turn,fake)
        row=self.row(turn);self.assertNotIn('never-show',row['error'])
        self.assertGreater(a.usage(self.path)['micro_usd'],0)
        with a.database(self.path) as db:self.assertEqual(db.execute('SELECT state FROM assistant_calls').fetchone()[0],'RESERVED')
        self.assertEqual(fake.call_count,1)

    def test_budget_stops_before_provider(self):
        turn=self.turn();fake=Mock()
        with patch.object(a,'DAILY_MICRO_USD',1):a.run(KI,self.path,turn,fake)
        fake.assert_not_called();self.assertEqual(a.usage(self.path)['calls'],0)

    def test_concurrent_reservations_respect_count_cap(self):
        turn=self.turn();results=[]
        def book():
            try:a.reserve(self.path,turn,{'messages':[]});results.append(True)
            except ValueError:results.append(False)
        with patch.object(a,'DAILY_CALLS',1):
            workers=[threading.Thread(target=book) for _ in range(5)]
            for w in workers:w.start()
            for w in workers:w.join()
        self.assertEqual(results.count(True),1)

    def test_call_limit_stops_tool_loop(self):
        turn=self.turn();fake=Mock(return_value=reply('company',{'ticker':'HUMA'}))
        a.run(KI,self.path,turn,fake)
        self.assertEqual(fake.call_count,a.MAX_CALLS);self.assertEqual(self.row(turn)['state'],'FAILED')
        self.assertEqual(fake.call_args.args[3]['response_format']['json_schema']['name'],'ki_assistant_answer')
        self.assertNotIn('tools',fake.call_args.args[3])

    def test_three_reads_then_normal_json_answer_through_real_http_adapter(self):
        turn=self.turn()
        final={'choices':[{'finish_reason':'stop','message':{'content':json.dumps(answer(['E1','E2','E3']))}}],
               'usage':{'prompt_tokens':8160,'completion_tokens':472}}
        bodies=[reply('company',{'ticker':'HUMA'}),reply('reviews',{'ticker':'HUMA'}),reply('top5',{}),final]
        responses=[Mock(status_code=200,headers={},json=Mock(return_value=b)) for b in bodies]
        with patch('requests.post',side_effect=responses) as post:
            a.run(KI,self.path,turn,REAL_HTTP)
        row=self.row(turn)
        self.assertEqual(row['state'],'DONE',row)
        self.assertEqual(len(json.loads(row['evidence'])),3)
        self.assertEqual(post.call_count,4)
        self.assertEqual(post.call_args.kwargs['json']['response_format']['type'],'json_schema')
        self.assertNotIn('tools',post.call_args.kwargs['json'])
        with a.database(self.path) as db:
            diagnostics=[json.loads(r[0]) for r in db.execute('SELECT payload FROM assistant_call_diagnostics')]
        self.assertEqual([d['finish_reason'] for d in diagnostics],['tool_calls']*3+['stop'])

    def test_complete_answer_tool_with_stop_is_validated_not_discarded(self):
        final=reply('answer',answer(['E1']))
        final['choices'][0]['finish_reason']='stop'
        turn=self.turn()
        fake=Mock(side_effect=[reply('company',{'ticker':'HUMA'}),final])
        a.run(KI,self.path,turn,fake)
        self.assertEqual(self.row(turn)['state'],'DONE')
        self.assertEqual(fake.call_count,2)

    def test_stop_answer_never_bypasses_evidence_checks(self):
        final=reply('answer',answer(['E999']))
        final['choices'][0]['finish_reason']='stop'
        turn=self.turn();fake=Mock(return_value=final)
        a.run(KI,self.path,turn,fake)
        self.assertEqual(self.row(turn)['state'],'FAILED');self.assertEqual(fake.call_count,1)

    def test_truncated_or_uncited_final_json_is_not_published(self):
        cases=[{'finish_reason':'length','message':{'content':json.dumps(answer(['E1']))}},
               {'finish_reason':'stop','message':{'content':json.dumps(answer(['E999']))}},
               {'finish_reason':'stop','message':{'content':'{incomplete'}},
               {'finish_reason':'stop','message':{'content':json.dumps(answer(['E1'])),'refusal':'refused'}}]
        for case in cases:
            turn=self.turn();fake=Mock(side_effect=[reply('company',{'ticker':'HUMA'})]*3+[{'choices':[case]}])
            a.run(KI,self.path,turn,fake)
            self.assertEqual(self.row(turn)['state'],'FAILED');self.assertEqual(fake.call_count,4)

    def test_context_byte_limit_prevents_call(self):
        turn=self.turn();fake=Mock()
        with patch.object(a,'MAX_REQUEST_BYTES',10):a.run(KI,self.path,turn,fake)
        fake.assert_not_called()

    def test_stale_worker_not_replayed(self):
        turn=self.turn()
        with a.database(self.path,True) as db:
            db.execute('UPDATE assistant_turns SET updated_at=? WHERE id=?',
                       ((datetime.now(timezone.utc)-timedelta(minutes=11)).isoformat(),turn))
        a.ensure(self.path);fake=Mock();a.run(KI,self.path,turn,fake)
        self.assertEqual(self.row(turn)['state'],'INTERRUPTED');fake.assert_not_called()

    def test_clear_thread_removes_contents_and_memory_but_preserves_usage(self):
        turn=self.turn()
        a.run(KI,self.path,turn,Mock(side_effect=[reply('company',{'ticker':'HUMA'}),reply('answer',answer(['E1']))]))
        count=a.usage(self.path)
        self.assertTrue(a.clear_thread(self.path,self.thread))
        row=self.row(turn)
        self.assertEqual(row['state'],'CLEARED');self.assertEqual(row['question'],'')
        self.assertIsNone(row['answer']);self.assertEqual(json.loads(row['evidence']),[])
        self.assertEqual(a.history(self.path,self.thread,'absent'),[])
        self.assertEqual(a.usage(self.path),count)

    def test_clear_button_erases_text_and_visible_history_without_provider(self):
        from streamlit.testing.v1 import AppTest
        turn=self.turn();a.run(KI,self.path,turn,Mock(return_value=reply('answer',answer())))
        script='import KI, ki_assistant\nfrom pathlib import Path\nki_assistant.render(KI,ki_assistant.ReadStore(Path('+repr(str(self.path))+')))'
        app=AppTest.from_string(script).run(timeout=20)
        app.text_area[0].input('Tekst do usunięcia')
        next(b for b in app.button if b.label=='Wyczyść pytanie i historię').click().run()
        self.assertFalse(app.exception)
        self.assertEqual(app.text_area[0].value,'');self.assertEqual(len(app.chat_message),0)

    def test_clear_thread_cannot_erase_running_turn(self):
        turn=self.turn()
        self.assertFalse(a.clear_thread(self.path,self.thread))
        self.assertEqual(self.row(turn)['state'],'RUNNING')

    def test_maintenance_blocks_before_provider(self):
        @contextmanager
        def unavailable():yield False
        turn=self.turn();fake=Mock()
        with patch.object(a,'provider_lease',unavailable):a.run(KI,self.path,turn,fake)
        fake.assert_not_called();self.assertEqual(self.row(turn)['state'],'FAILED')

    def test_missing_data_and_future_claims_are_not_fabricated_by_tools(self):
        result=a.Reader(self.path,KI).run('company',{'ticker':'UNKNOWN'})['data']
        self.assertEqual(result['snapshots_newest_first'],[]);self.assertIsNone(result['orchestrator'])

    def test_scrub_prompt_and_selected_nested_sources(self):
        value=a.scrub({'title':'tvly-do-not-print','API_KEY':'private','provider':{'raw_response':'private'},
                       'safe':{'note':'Bearer private-value'}})
        self.assertNotIn('private',str(value));self.assertNotIn('tvly-',str(value))
        turn=self.turn('Sprawdź sk-user-pasted-secret')
        self.assertNotIn('sk-',self.row(turn)['question'])

    def test_question_is_not_silently_truncated(self):
        with self.assertRaises(ValueError):self.turn('a'*3001)
        with self.assertRaises(ValueError):self.turn('   ')

    def test_actual_top5_adapter_uses_existing_filter(self):
        import test_final_company_review_20261106 as fixtures
        import selected_opportunities as top
        f=fixtures.FinalCompanyReviewTests();f.setUp();self.addCleanup(f.doCleanups)
        f.prepare(2,with_plan=True);f.finish_members('INFORM')
        KI.company_review.finalize(KI,f.store,fixtures.NOW)
        collect=top.collect
        with patch.object(top,'collect',side_effect=lambda api,store:collect(api,store,fixtures.NOW+timedelta(minutes=2))):
            data=a.Reader(f.store.path,KI).run('top5',{})['data']
        self.assertEqual(len(data['cards']),2)
        self.assertTrue(all(c['trade_plan']['sl']<c['trade_plan']['entry']<c['trade_plan']['tp1'] for c in data['cards']))

    def test_ui_open_refresh_switch_and_evidence_no_provider(self):
        from streamlit.testing.v1 import AppTest
        turn=self.turn();a.run(KI,self.path,turn,Mock(side_effect=[reply('company',{'ticker':'HUMA'}),reply('answer',answer(['E1']))]))
        script='import KI, ki_assistant\nfrom pathlib import Path\nki_assistant.render(KI,ki_assistant.ReadStore(Path('+repr(str(self.path))+')))'
        app=AppTest.from_string(script).run(timeout=20)
        self.assertFalse(app.exception)
        self.assertTrue(any('Asystent KI' in h.value for h in app.subheader))
        self.assertEqual(len(app.chat_message),2)
        next(b for b in app.button if b.label=='Nowa rozmowa').click().run()
        self.assertFalse(app.exception);self.assertEqual(len(app.chat_message),0)
        app.run();self.assertFalse(app.exception)


if __name__=='__main__':
    unittest.main()
