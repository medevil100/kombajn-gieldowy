"""Regresja A1: trwały zapis silnika zadania ręcznego, odczyt przy wznowieniu
i wybór dostawcy. Rzeczywiste funkcje KI + tymczasowa SQLite.
Bez mocków, atrap, płatnych API, Research i Telegrama."""
import json
import tempfile
import unittest
from pathlib import Path
import KI


def stored_context(engine='openai', with_engine=True, status='SUBMITTED'):
    context={'ticker':'AAT.WA','report_version':3,'purpose':'chat',
             'snapshot':{'ticker':'AAT.WA','interval':'1h','currency':'PLN',
                         'acquired_at':'2026-10-08T11:33:31+00:00',
                         'candle_time':'2026-10-08T10:00:00+00:00',
                         'candle_end':'2026-10-08T11:00:00+00:00',
                         'candle_status':'CLOSED','price':1.66,'volume':6589,
                         'average_volume':4907,'rvol':1.34,
                         'ohlc':{'open':1.66,'high':1.66,'low':1.66,'close':1.66},
                         'previous_closed':{'close':1.65,'open':1.65,'volume':3000,'rvol':.61},
                         'indicators':{'ma_fast':1.677,'ma_slow':1.6647,'rsi':43.64,'adx':18.63}},
             'research':{'status':status,'request_id':'r1-saved-id',
                         'cutoff':'2026-10-08T11:33:31+00:00','sources':[]}}
    if with_engine:
        context['engine']=engine
    return context


def sample_request():
    return KI.gpt_chat_request('Co pokazują dane?',stored_context(),[])


class ManualEngineValueTests(unittest.TestCase):
    def test_supported_values_are_accepted(self):
        for value in ('openai',):
            self.assertEqual(KI.manual_engine(value),value)

    def test_unknown_or_missing_value_is_rejected(self):
        for value in ('gpt5','OpenAI','',None,7,True):
            with self.subTest(value=value), self.assertRaises(ValueError):
                KI.manual_engine(value)

    def test_stored_engine_is_read_verbatim(self):
        with self.assertRaises(ValueError):KI.saved_manual_engine({'engine':'deepseek'})
        self.assertEqual(KI.saved_manual_engine({'engine':'openai'}),'openai')

    def test_task_without_saved_engine_cannot_resume(self):
        for context in ({},{'engine':None},{'engine':'gpt5'},None):
            with self.subTest(context=context), self.assertRaises(ValueError):
                KI.saved_manual_engine(context)


class ManualProviderTests(unittest.TestCase):
    def test_retired_provider_is_rejected_before_any_network_or_request_changes(self):
        req=sample_request();before=KI.json_text(req)
        with self.assertRaises(ValueError):
            KI.manual_provider('deepseek',{'DEEPSEEK_API_KEY':'ds','OPENAI_API_KEY':'oa'},req)
        self.assertEqual(KI.json_text(req),before)

    def test_automatic_retired_provider_is_rejected_without_request(self):
        with self.assertRaises(KI.ServiceError):
            KI.analyze_event({'snapshot':{}},{'prepared_ai_request':{'model':'gpt-4o-mini'}},{},engine='deepseek')

    def test_openai_keeps_existing_model_and_endpoint(self):
        req=sample_request()
        label,url,key=KI.manual_provider('openai',{'OPENAI_API_KEY':'oa'},req)
        self.assertEqual((label,key),('OpenAI','oa'))
        self.assertEqual(url,'https://api.openai.com/v1/chat/completions')
        self.assertEqual(req['model'],'gpt-4o-mini')
        self.assertIn('json_schema',req['response_format'])

    def test_openai_does_not_require_deepseek_key(self):
        KI.manual_provider('openai',{'OPENAI_API_KEY':'oa'},sample_request())

    def test_openai_without_its_key_is_rejected(self):
        with self.assertRaises(ValueError):
            KI.manual_provider('openai',{'DEEPSEEK_API_KEY':'ds'},sample_request())

    def test_key_only_validation_without_request(self):
        KI.manual_provider('openai',{'OPENAI_API_KEY':'oa'})
        with self.assertRaises(ValueError):
            KI.manual_provider('deepseek',{})

class ManualTurnContextTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.store=KI.Store(Path(self.temp.name)/'engine.sqlite3')

    def tearDown(self):
        self.temp.cleanup()

    def test_new_turn_context_stores_explicit_engine(self):
        for engine in ('openai',):
            context=KI.manual_turn_context(self.store,'MREO','chat',engine,False)
            self.assertEqual(context['engine'],engine)
            self.assertEqual(context['research'],{'sources':[],'status':'DISABLED'})

    def test_new_turn_context_rejects_unknown_engine(self):
        with self.assertRaises(ValueError):
            KI.manual_turn_context(self.store,'MREO','chat','gpt5',False)

    def test_engine_is_persisted_with_the_created_turn(self):
        snapshot={'ticker':'MREO','interval':'1h','acquired_at':'2026-10-11T18:00:00+00:00',
                  'candle_time':'2026-10-11T18:00:00+00:00','candle_end':'2026-10-11T19:00:00+00:00',
                  'candle_status':'CLOSED','price':1.66,'currency':'PLN','volume':1000,'rvol':1.1,
                  'ohlc':{'open':1.66,'high':1.7,'low':1.6,'close':1.66},'indicators':{}}
        with self.store.transaction() as c:
            c.execute("INSERT INTO observations(ticker,interval,candle_time,acquired_at,candle_status,payload) VALUES(?,?,?,?,?,?)",
                      ('MREO','1h',snapshot['candle_time'],snapshot['acquired_at'],'CLOSED',KI.json_text(snapshot)))
        context=KI.manual_turn_context(self.store,'MREO','chat','openai',True)
        turn=KI.begin_gpt_chat(self.store,'Pytanie do modelu',context)
        with self.store.connection() as c:
            saved=json.loads(c.execute('SELECT context FROM gpt_chat_turns WHERE id=?',(turn,)).fetchone()[0])
        self.assertEqual(saved['engine'],'openai')
        self.assertEqual(saved['research']['status'],'PENDING')


class ResumeStopsBeforeChangeTests(unittest.TestCase):
    """resume_manual_research must stop before any status change or service call."""
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.store=KI.Store(Path(self.temp.name)/'resume.sqlite3')

    def tearDown(self):
        self.temp.cleanup()

    def insert(self,context):
        with self.store.transaction() as c:
            c.execute("INSERT INTO gpt_chat_turns(id,question,context,state,created_at) VALUES(?,?,?,'REVIEW_REQUIRED',?)",
                      ('turn-1','Pytanie',KI.json_text(context),KI.utc_now()))

    def snapshot_row(self):
        with self.store.connection() as c:
            row=c.execute("SELECT state,context,error,finished_at FROM gpt_chat_turns WHERE id='turn-1'").fetchone()
        return (row['state'],row['context'],row['error'],row['finished_at'])

    def assert_untouched(self,context):
        self.insert(context)
        before=self.snapshot_row()
        with self.assertRaises(ValueError):
            KI.resume_manual_research(self.store,'turn-1')
        self.assertEqual(self.snapshot_row(),before)
        with self.store.connection() as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM outbox').fetchone()[0],0)
            self.assertEqual(c.execute('SELECT COUNT(*) FROM events').fetchone()[0],0)

    def test_task_without_engine_is_not_modified(self):
        self.assert_untouched(stored_context(with_engine=False))

    def test_retired_engine_is_not_modified_or_redirected(self):
        self.assert_untouched(stored_context(engine='deepseek'))

    def test_unknown_stored_engine_is_not_modified(self):
        self.assert_untouched(stored_context(engine='gpt5'))

    def test_missing_engine_message_is_explicit(self):
        self.insert(stored_context(with_engine=False))
        with self.assertRaises(ValueError) as raised:
            KI.resume_manual_research(self.store,'turn-1')
        self.assertIn('silnika',str(raised.exception))


if __name__=='__main__':
    unittest.main()
