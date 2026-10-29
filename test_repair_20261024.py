"""Regresje lokalne: prawdziwe funkcje KI i SQLite, bez usług oraz atrap."""
import copy
from contextlib import closing
import json
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

import KI

NOW = datetime(2026, 10, 12, 14, 30, tzinfo=timezone.utc)


def daily(day, close=1.0):
    return {'session_date': day, 'status': 'CLOSED', 'open': close,
            'high': close * 1.1, 'low': close * .9, 'close': close, 'volume': 100000.0}


class RepairTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = KI.Store(Path(self.tmp.name) / 'repair.sqlite3')
        self.snap = KI.opportunity_test_snapshot(NOW, ticker='STX.WA', price=1.3)
        self.snap['indicators'] = {'rsi': 55.126, 'adx': 30.0}
        self.context = {'sources': [{'id': 'S1', 'content': 'Raport emitenta. Bez prognozy.',
                                    'url': 'https://example.org/report'}]}

    def result(self):
        return {'technical': [{'metric': 'rsi', 'interpretation': 'RSI wynosi 55,13.'}],
                'context': [{'source_id': 'S1', 'fact': 'Raport emitenta.'}],
                'hypotheses': ['Możliwa kontynuacja ruchu.'],
                'risks': ['Ruch może się odwrócić.'], 'missing': ['Brak zleceń.']}

    def job(self):
        with self.store.transaction() as c:
            c.execute('INSERT INTO events VALUES(?,?,?,?,?)',
                      ('e', 'STX.WA', '1h', NOW.isoformat(), KI.json_text({'snapshot': self.snap})))
            c.execute('INSERT INTO analysis_jobs(event_id,state,context,updated_at) VALUES(?,?,?,?)',
                      ('e', 'BUSY_AI', KI.json_text(self.context), NOW.isoformat()))

    def test_numbers_are_linked_only_to_named_metric_and_decimal_rounding(self):
        for text in ('RSI wynosi 30.', 'RSI wynosi 70.', 'RSI wynosi 55,13%.',
                     'RSI wynosi 55,13 USD.', 'RSI14 wynosi 55,13.', 'RSI wynosi 5.513e1.'):
            with self.subTest(text=text):
                result=self.result(); result['technical'][0]['interpretation']=text
                clean=KI.validate_event_analysis(result,self.snap,self.context)
                self.assertEqual(clean['technical'],[])
                self.assertEqual(clean['hypotheses'],[])
        clean=KI.validate_event_analysis(self.result(),self.snap,self.context)
        self.assertEqual(clean,self.result())

    def test_cleaning_is_deep_nonmutating_stable_and_ignores_provider_diagnostics(self):
        result=self.result(); result['context'][0]['fact']='Nie ma tego w źródle.'
        result['quality_issues']=['Fałszywe zaufane ostrzeżenie modelu.']
        before=copy.deepcopy(result)
        clean=KI.validate_event_analysis(result,self.snap,self.context)
        self.assertEqual(result,before)
        self.assertEqual(clean['context'],[])
        self.assertEqual(clean['technical'],result['technical'])
        for key in ('hypotheses','risks','missing'):self.assertEqual(clean[key],[])
        self.assertNotIn(result['quality_issues'][0],clean['quality_issues'])
        self.assertEqual(clean,KI.validate_event_analysis(clean,self.snap,self.context))
        self.assertEqual(len(clean['quality_issues']),len(set(clean['quality_issues'])))

    def test_invalid_technical_keeps_other_technical_and_good_quote(self):
        result=self.result(); result['technical'].append({'metric':'adx','interpretation':'ADX wynosi 70.'})
        clean=KI.validate_event_analysis(result,self.snap,self.context)
        self.assertEqual(clean['technical'],result['technical'][:1])
        self.assertEqual(clean['context'],result['context'])
        self.assertEqual(clean['risks'],[])

    def test_quote_word_limit_and_independent_source(self):
        words=' '.join(['a']*26)
        self.context['sources'].append({'id':'S2','content':words})
        result=self.result();result['context'].append({'source_id':'S2','fact':words})
        clean=KI.validate_event_analysis(result,self.snap,self.context)
        self.assertEqual(clean['context'],result['context'][:1])

    def test_hypotheses_risks_missing_reject_numbers_and_advice(self):
        result=self.result()
        for key in ('hypotheses','risks','missing'):result[key]=['Wartość 30.','BUY teraz.','Brak danych.']
        clean=KI.validate_event_analysis(result,self.snap,self.context)
        for key in ('hypotheses','risks','missing'):self.assertEqual(clean[key],['Brak danych.'])

    def test_full_raw_response_survives_success_and_rejection(self):
        body={'id':'raw','extra':{'nested':['oryginał']},'choices':[{'finish_reason':'stop','message':{'content':KI.json_text(self.result())}}]}
        result,metadata=KI.parse_event_analysis_response(body,self.snap,self.context)
        self.assertEqual(metadata['raw_response'],body)
        metadata['raw_response']['extra']['nested'].append('kopia')
        self.assertEqual(body['extra']['nested'],['oryginał'])
        body['choices'][0]['finish_reason']='length'
        with self.assertRaises(KI.AnalysisRejected) as caught:KI.parse_event_analysis_response(body,self.snap,self.context)
        self.assertEqual(caught.exception.payload['raw_response'],body)

    def test_empty_analysis_is_saved_and_pending_and_preview_invalidated(self):
        self.job()
        with self.store.transaction() as c:
            for status in ('PENDING','PREVIEW'):
                c.execute('INSERT INTO outbox(id,event_id,kind,message,status,created_at) VALUES(?,?,?,?,?,?)',
                          (status,'e','ANALYSIS','stary tekst',status,NOW.isoformat()))
        result=self.result();result['technical']=[];result['hypotheses']=[];result['risks']=[]
        self.assertFalse(KI.analysis_has_valid_conclusions(result))
        KI.finish_analysis(self.store,'e',result,{'raw_response':{'full':'raw'}},now=NOW)
        with self.store.connection() as c:
            row=c.execute('SELECT state,result FROM analysis_jobs').fetchone()
            self.assertEqual(row['state'],'REVIEW_REQUIRED')
            self.assertEqual(json.loads(row['result'])['provider']['raw_response'],{'full':'raw'})
            self.assertEqual([r[0] for r in c.execute('SELECT status FROM outbox')],['FILTERED','FILTERED'])
        self.assertIn('Wymaga sprawdzenia',KI.analysis_message('e',{'snapshot':self.snap},self.context,result))

    def test_finished_analysis_and_publication_are_atomic(self):
        self.job()
        with self.store.connection() as c:
            c.execute("CREATE TRIGGER reject BEFORE INSERT ON outbox BEGIN SELECT RAISE(ABORT,'test'); END")
        with self.assertRaises(sqlite3.IntegrityError):KI.finish_analysis(self.store,'e',self.result(),{},now=NOW)
        with self.store.connection() as c:
            self.assertEqual(c.execute('SELECT state,result FROM analysis_jobs').fetchone()[:],('BUSY_AI',None))

    def test_diagnostics_are_visible_in_short_message(self):
        snap=KI.opportunity_test_snapshot(NOW,'STX.WA',1.3)
        snap['indicators']=self.snap['indicators']
        ranking=KI.opportunity_local_rank(snap)
        result=self.result();result['context'][0]['fact']='Nieprawidłowy cytat.'
        result['technical'].append({'metric':'adx','interpretation':'ADX opisuje siłę, nie kierunek ruchu.'})
        clean=KI.validate_event_analysis(result,snap,self.context)
        text=KI.opportunity_message('e',{'snapshot':snap,'ranking':ranking},self.context,clean)
        self.assertIn('Analiza częściowa',text)
        self.assertNotIn('Nieprawidłowy cytat.',text)

    def seed(self):
        KI._save_daily_history(self.store,'STX.WA',[daily('2026-10-08',.9),daily('2026-10-09',1.)],NOW)

    def reading(self,minutes,price=1.3):
        at=NOW+timedelta(minutes=minutes)
        snap=KI.opportunity_test_snapshot(at,'STX.WA',price)
        snap['volume']=100000.+minutes*1000
        snap['ohlc']={'open':1.,'high':1.4,'low':1.,'close':price}
        return snap

    def test_friday_reference_monday_multiple_reads_and_restart(self):
        self.seed()
        first=KI.record_price_matrix_read(self.store,self.reading(0),2.)
        self.assertAlmostEqual(first['change_pct'],30.)
        self.assertEqual(first['consecutive_reads'],0)
        self.assertEqual(first['reference_session'],'2026-10-09')
        self.store=KI.Store(self.store.path)
        later=KI.record_price_matrix_read(self.store,self.reading(15,1.25),2.)
        self.assertEqual(later['anchor_price'],1.)
        self.assertAlmostEqual(later['change_pct'],25.)
        self.assertEqual(len(KI.load_daily_candles(self.store,'STX.WA')),2)

    def test_new_session_changes_reference_and_restarts_proofs(self):
        self.seed();KI.record_price_matrix_read(self.store,self.reading(0),2.)
        KI._save_daily_history(self.store,'STX.WA',[daily('2026-10-12',1.25)],NOW+timedelta(days=1))
        row=KI.record_price_matrix_read(self.store,self.reading(24*60,1.3),2.)
        self.assertEqual(row['anchor_price'],1.25)
        self.assertEqual(row['reference_session'],'2026-10-12')
        self.assertEqual(row['consecutive_reads'],0)

    def test_missing_reference_blocks_matrix_and_opportunity(self):
        snap=self.reading(0)
        result=KI.detect_market(self.store,snap,{'price_matrix_enabled':True})
        self.assertEqual(result['status'],'MISSING_DAILY_REFERENCE')
        self.assertIsNone(result['price_matrix']['anchor_price'])
        self.assertFalse(KI.two_candle_candidate({**snap,'price_matrix':result['price_matrix']},NOW))
        self.assertEqual(KI.polish_status(result['status']),'Niepotwierdzona baza poprzedniej sesji — kwalifikacja wstrzymana')

    def test_daily_upserts_and_rejected_batch_are_atomic(self):
        self.seed();self.seed()
        self.assertEqual(len(KI.load_daily_candles(self.store,'STX.WA')),2)
        for change in ({'status':'OPEN'},{'close':0},{'high':.5},{'volume':None},{'volume':-1},
                       {'end':'2027-10-09T17:00:00+02:00'}):
            with self.subTest(change=change):
                with self.assertRaises(ValueError):KI._save_daily_history(self.store,'STX.WA',[daily('2026-10-07'),{**daily('2026-10-09'),**change}],NOW)
                self.assertEqual(len(KI.load_daily_candles(self.store,'STX.WA')),2)

    def test_refresh_once_per_day_and_again_after_session(self):
        self.seed()
        self.assertFalse(KI.daily_history_refresh_due(self.store,'STX.WA',NOW+timedelta(minutes=15)))
        self.assertTrue(KI.daily_history_refresh_due(self.store,'STX.WA',NOW+timedelta(hours=1)))
        KI._save_daily_history(self.store,'STX.WA',[daily('2026-10-12',1.2)],NOW+timedelta(hours=1))
        self.assertFalse(KI.daily_history_refresh_due(self.store,'STX.WA',NOW+timedelta(hours=2)))
        self.assertTrue(KI.daily_history_refresh_due(self.store,'STX.WA',NOW+timedelta(days=1)))

    def test_timezone_reference_uses_exchange_day_not_utc(self):
        ticker='AAA';now=datetime(2026,10,13,0,30,tzinfo=timezone.utc)
        KI._save_daily_history(self.store,ticker,[daily('2026-10-09',1.),daily('2026-10-12',1.2)],now)
        with self.store.connection() as c:
            self.assertEqual(KI._daily_reference(c,ticker,now)['session_date'],'2026-10-09')
            self.assertEqual(KI._daily_reference(c,ticker,now+timedelta(hours=5))['session_date'],'2026-10-12')
        self.assertEqual(str(KI.exchange_zone('STX.WA')),'Europe/Warsaw')

    def test_daily_never_becomes_hourly_trigger(self):
        snap=self.reading(0);snap['interval']='1d'
        self.assertFalse(KI.two_candle_candidate(snap,NOW))
        self.assertIsNone(KI.score_growth_candidate(snap,{'price':1.},now=NOW))

    def test_placeholders_and_missing_text_are_not_conclusions(self):
        result={'technical':[],'context':[{'fact':'Raport.'}],'missing':['Brak danych.'],
                'hypotheses':['[brak treści]'],'risks':['Wymaga sprawdzenia.']}
        self.assertFalse(KI.analysis_has_valid_conclusions(result))

    def test_automatic_config_keeps_manual_config_independent(self):
        settings={'market_interval':'1d','auto_scan_interval':60}
        self.assertEqual(KI.market_config(settings)['market_interval'],'1d')
        self.assertEqual(KI.automatic_market_config(settings)['market_interval'],'1h')
        self.assertEqual(KI.automatic_market_config(settings)['auto_scan_interval'],15)
        self.assertEqual(KI.automatic_market_config({'auto_scan_interval':0})['auto_scan_interval'],0)

    def test_older_read_never_rolls_back_matrix_even_across_session(self):
        self.seed();KI.record_price_matrix_read(self.store,self.reading(15),2.)
        before=self.store.get_price_matrix('STX.WA')
        row=KI.record_price_matrix_read(self.store,self.reading(0,1.01),2.)
        self.assertEqual(row['read_status'],'OUT_OF_ORDER')
        self.assertEqual(self.store.get_price_matrix('STX.WA'),before)

    def test_future_daily_session_rejected_even_when_marked_closed(self):
        with self.assertRaises(ValueError):
            KI._save_daily_history(self.store,'STX.WA',[daily('2026-10-13')],NOW)
        self.assertEqual(KI.load_daily_candles(self.store,'STX.WA'),[])

    def test_history_matrix_confirmation_analysis_queue_flow(self):
        # Start earlier so all four reads remain inside the GPW session.
        base=NOW-timedelta(hours=1)
        self.seed();self.store.save_section('tickers',['STX.WA'])
        snapshots=[]
        for minutes in (0,15,30,45):
            at=base+timedelta(minutes=minutes)
            snap=KI.opportunity_test_snapshot(at,'STX.WA',1.3)
            snap['volume']=100000+minutes*1000
            result=KI.detect_market(self.store,snap,{'price_matrix_enabled':True,'price_threshold_pct':2.})
            snap={**snap,'price_matrix':result['price_matrix']};snapshots.append(snap)
            row=KI.record_opportunity(self.store,snap,'cycle',at)
        self.assertEqual([s['price_matrix']['consecutive_reads'] for s in snapshots],[0,1,2,3])
        at=base+timedelta(minutes=45)
        self.assertEqual(row['state'],'CONFIRMED')
        self.assertEqual(len(KI.reserve_opportunities(self.store,'cycle',at)),1)
        self.assertTrue(KI.queue_opportunity(self.store,row['sequence_id'],{},True,at))
        eid=row['sequence_id'];self.assertIsNotNone(KI.claim_analysis(self.store,eid,at))
        context={'sources':[]};KI.save_analysis_context(self.store,eid,context)
        self.assertIsNotNone(KI.claim_analysis(self.store,eid,at))
        result={'technical':[{'metric':'rsi','interpretation':'Wskaźnik wskazuje przewagę ruchu.'},{'metric':'ma_fast','interpretation':'Cena powyżej szybkiej średniej wspiera ruch.'}],
                'context':[],'hypotheses':[],'risks':[],'missing':[]}
        KI.finish_analysis(self.store,eid,result,{'raw_response':{'test':'lokalny'}},at)
        with self.store.connection() as c:
            self.assertEqual(c.execute('SELECT state FROM analysis_jobs').fetchone()[0],'DONE')
            self.assertEqual(c.execute('SELECT status FROM outbox').fetchone()[0],'PENDING')

    def test_additive_schema_preserves_existing_data_and_old_code_can_open(self):
        self.store.save_section('tickers',['STX.WA']);self.seed()
        self.store=KI.Store(self.store.path)
        self.assertEqual(self.store.load_section('tickers',[]),['STX.WA'])
        with closing(sqlite3.connect(self.store.path)) as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM daily_candles').fetchone()[0],2)
            self.assertEqual(c.execute("SELECT value FROM metadata WHERE key='schema_version'").fetchone()[0],'2')


if __name__=='__main__':unittest.main(verbosity=2)
