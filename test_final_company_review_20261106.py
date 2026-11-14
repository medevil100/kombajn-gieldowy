"""Independent issuer prompts, full saved reports and one durable digest. No HTTP."""
from contextlib import ExitStack
from contextlib import redirect_stdout
import copy
import io
from datetime import datetime,timedelta,timezone
import json
from pathlib import Path
import tempfile
import shutil
import sys
import types
import unittest
from unittest.mock import patch

import KI
import final_company_review as review
import ki2_ops_guard
import sl_tp
from test_company_narrative_20261113 import fixture_narrative


NOW=datetime(2026,11,6,15,30,tzinfo=timezone.utc)


def model_transport(response):
    """Fixture provider supports frozen legacy replies and the evidence-ID wire format."""
    def reply(*args,**kwargs):
        request=args[3] if len(args)>3 else kwargs.get('payload',{})
        if not KI.evidence_review.is_request(request):return copy.deepcopy(response)
        book=json.loads(request['messages'][-1]['content'])['evidence_review']
        old=json.loads(response['choices'][0]['message']['content'])
        attention=(old.get('final_review') or {}).get('attention','INFORM')
        support='S_ALIGNMENT' if 'S_ALIGNMENT' in book['supports'] else 'S_DETECTION'
        limit='L_ACTIVITY_SCOPE' if 'L_ACTIVITY_SCOPE' in book['limits'] else 'L_FUTURE'
        wire={'verdict':attention,
              'price_evidence':next(iter(book['price'])),'momentum_evidence':[next(iter(book['momentum']))],
              'supporting_evidence':[support],'limiting_evidence':[limit],
              'watch_condition':next(iter(book['conditions'])),'source_quote':'NONE'}
        if book.get('coordination'):
            primary=support if attention=='INFORM' else book['coordination']['panel_reasons'][0]
            if attention=='PANEL_ONLY':wire['limiting_evidence']=[primary]
            wire.pop('verdict');wire.pop('source_quote')
            wire['decision']={'verdict':attention,'primary_reason':primary,'source_quote':'NONE'}
            if 'narrative' in request['response_format']['json_schema']['schema']['properties']:wire['narrative']=fixture_narrative()
        result=copy.deepcopy(response);result['choices'][0]['message']['content']=json.dumps(wire)
        return result
    return reply


class FinalCompanyReviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.store=KI.Store(Path(self.tmp.name)/'review.sqlite3')
        class Clock(datetime):
            @classmethod
            def now(cls,tz=None):return NOW if tz else NOW.replace(tzinfo=None)
        self.stack=ExitStack();self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(KI,'datetime',Clock))
        self.stack.enter_context(patch.object(sl_tp,'datetime',Clock))
        self.stack.enter_context(patch.object(ki2_ops_guard,'LOCK_PATH',Path(self.tmp.name)/'test-only-absent.lock'))
        self.store.save_section('settings',{'pipeline_enabled':True,'telegram_enabled':True,
            'auto_scan_interval':15,'price_threshold_pct':2.,review.SETTING:True})

    def candidates(self,n=3,with_plan=False,direction=1):
        tickers=['A'+str(i)+('.WA' if i%2==0 else '') for i in range(n)]
        self.store.save_section('tickers',tickers)
        for ticker in tickers:
            KI._save_daily_history(self.store,ticker,[{'session_date':'2026-11-05','status':'CLOSED',
                  'open':100.,'high':100.,'low':100.,'close':100.,'volume':10000}],NOW)
            for minute,raw_price in ((-45,100.),(-30,105.),(-15,105.),(0,105.)):
                price=100.+direction*(raw_price-100.)
                at=NOW+timedelta(minutes=minute)
                s=KI.opportunity_test_snapshot(at,ticker,price)
                s.update(currency='PLN' if ticker.endswith('.WA') else 'USD',volume=200000.+(minute+45)*1000.,
                    ohlc={'open':100.,'high':max(100.,price)+.1,'low':min(100.,price)-.1,'close':price})
                if direction<0:s['indicators'].update(ma_fast=101.,ma_slow=102.,rsi=40.,last_macd_hist=-.1,plus_di=10.,minus_di=30.)
                opening,closing=review.session_context.bounds('XWAR' if ticker.endswith('.WA') else 'XNYS','2026-11-06')
                start=opening+timedelta(hours=int((at-opening).total_seconds()//3600))
                end=min(start+timedelta(hours=1),closing)
                s.update(candle_time=start.isoformat(),candle_end=end.isoformat(),
                    partial_interval=(end-start).total_seconds()<3600,
                    status_basis='session_end' if (end-start).total_seconds()<3600 else 'interval')
                history=[];bar_start=opening
                while bar_start<start:
                    history.append({'time':bar_start.isoformat(),'end':(bar_start+timedelta(hours=1)).isoformat(),
                        'status':'CLOSED','open':100.,'high':105.1 if direction>0 else 100.1,
                        'low':99.9 if direction>0 else 94.9,'close':104.5 if direction>0 else 95.5,'volume':200000.})
                    bar_start+=timedelta(hours=1)
                if history:s['previous_closed']={**history[-1],'rvol':2.,'average_volume':100000.}
                history.append({**s['ohlc'],'time':start.isoformat(),'end':end.isoformat(),'status':'OPEN','volume':s['volume']})
                if with_plan:
                    past=[]
                    for index in range(30):
                        beginning=opening-timedelta(hours=31-index)
                        past.append({'time':beginning.isoformat(),'end':(beginning+timedelta(hours=1)).isoformat(),
                            'status':'CLOSED','open':100.,'close':100.,'volume':100000.,
                            'low':90. if index in (4,14,24) else 95.,
                            'high':130. if index==8 else 150. if index==18 else 110.})
                    history=past+history;s['indicators']['atr']=5.
                s['chart_history']=history
                result=KI.detect_market(self.store,s,{'price_matrix_enabled':True,'price_threshold_pct':2.,'auto_scan_interval':15})
                s={**s,'price_matrix':result['price_matrix']}
                KI.record_opportunity(self.store,s,'cycle',at)
        return KI.reserve_opportunities(self.store,'cycle',NOW)

    def prepare(self,n=3,with_plan=False):
        selected=self.candidates(n,with_plan)
        self.assertEqual(len(selected),n)
        with patch.object(KI,'fetch_opportunity_spread',return_value={}) as fetch:
            batch=review.prepare(KI,self.store,'cycle',selected,NOW)
        return batch,fetch.call_count

    def rows(self,table):
        with self.store.connection() as c:return [dict(r) for r in c.execute('SELECT * FROM '+table)]

    def answer(self,attention='INFORM'):
        return {'technical':[
            {'metric':'ma_fast','interpretation':'Cena powyżej szybkiej średniej wspiera wzrost.'},
            {'metric':'rsi','interpretation':'Momentum RSI jest zgodne ze wzrostem.'}],
            'context':[],'hypotheses':[],'risks':['Ruch ceny może zostać zanegowany.'],
            'missing':['Nie ustalono przyczyny ruchu.'],
            'assessment':{
                'movement':'Przebieg sesji pokazuje wzrost ceny od otwarcia i zgodność ze wskazaniami technicznymi. Cena pozostaje powyżej szybkiej średniej, a momentum wspiera kierunek. Nie stanowi to dowodu przyszłej kontynuacji.',
                'activity':'Wolumen bieżącej świecy już przekracza średnią pełnych godzin. Jest to pomiar częściowy, a nie wynik zakończonej godziny. Obserwacja aktywności pozostaje potrzebna.',
                'risk':'Brak ofert ogranicza ocenę wykonania. Poziomy techniczne nie stanowią potwierdzenia realizacji transakcji. Brak danych do pełnego planu wymaga sprawdzenia ograniczeń w raporcie.'},
            'decision':{'verdict':'ALIGNED','reason_codes':['TECH_SUPPORT']},
            'final_review':{'attention':attention,'explanation':'Zgodność kierunku z ceną i momentum oraz nowa aktywność uzasadniają obserwację tej spółki; dalszy ruch nie jest przesądzony.'}}

    def finish_members(self,attention='INFORM'):
        with self.store.transaction() as c:
            for job in c.execute('SELECT * FROM analysis_jobs').fetchall():
                ev=KI.load_payload(c.execute('SELECT payload FROM events WHERE id=?',(job['event_id'],)).fetchone()[0])
                ctx={'sources':[],'cutoff':ev['snapshot']['acquired_at']}
                ctx['analysis_manifest']=KI.build_analysis_manifest(ev,ctx)
                c.execute("UPDATE analysis_jobs SET state='BUSY_AI',context=? WHERE event_id=?",(KI.json_text(ctx),job['event_id']))
        for job in self.rows('analysis_jobs'):
            KI.finish_analysis(self.store,job['event_id'],self.answer(attention),{'model':'mock','usage':{'total_tokens':1}},NOW)

    def test_cap_six_without_losing_remaining_local_candidates(self):
        batch,calls=self.prepare(9)
        self.assertIsNotNone(batch);self.assertEqual(calls,6)
        self.assertEqual(len(self.rows('analysis_jobs')),6)
        self.assertEqual(len(self.rows('opportunities')),9)
        pool=KI.load_payload(self.rows('company_review_batches')[0]['payload'])['pool']
        self.assertEqual(len(pool),9)
        self.assertEqual(sum(r['state']=='CYCLE_LIMIT' for r in pool),3)
        self.assertTrue(all(KI.load_payload(r['payload'])['company_review_batch']==batch for r in self.rows('events')))

    def test_full_reports_stay_independent_and_only_one_digest_is_queued(self):
        self.prepare();self.finish_members()
        self.assertEqual(self.rows('outbox'),[])
        self.assertTrue(review.finalize(KI,self.store,NOW))
        messages=self.rows('outbox');self.assertEqual(len(messages),1)
        self.assertEqual(messages[0]['kind'],'FINAL_COMPANY_DIGEST')
        self.assertEqual(messages[0]['status'],'PENDING')
        self.assertLess(len(messages[0]['message']),3900)
        self.assertIn('A0.WA',messages[0]['message']);self.assertIn('A1',messages[0]['message'])
        for job in self.rows('analysis_jobs'):
            self.assertEqual(job['state'],'DONE')
            saved=KI.load_payload(job['result'])['analysis']
            self.assertGreater(len(saved['assessment']['movement']),150)
        self.assertFalse(review.finalize(KI,self.store,NOW))
        claimed=KI.claim_delivery(self.store,now=NOW)
        self.assertEqual(claimed['kind'],'FINAL_COMPANY_DIGEST')
        self.assertIsNone(KI.claim_delivery(self.store,now=NOW))

    def test_panel_only_is_silence_not_forced_minimum_three(self):
        self.prepare(2);self.finish_members('PANEL_ONLY')
        self.assertTrue(review.finalize(KI,self.store,NOW))
        self.assertEqual(self.rows('outbox'),[])
        self.assertEqual(len(self.rows('analysis_jobs')),2)
        self.assertEqual(self.rows('company_review_batches')[0]['state'],'EMPTY')

    def test_slot_and_unchanged_or_inflight_deduplication_survive_restart(self):
        self.prepare(2)
        restarted=KI.Store(self.store.path)
        self.assertIsNone(review.prepare(KI,restarted,'other',[],NOW))
        self.assertEqual(len(self.rows('company_review_batches')),1)
        self.assertEqual(len(self.rows('company_review_seen')),2)
        with self.store.transaction() as c:
            c.execute("UPDATE opportunities SET state='CONFIRMED',cycle_id='later'")
        selected=KI.reserve_opportunities(self.store,'later',NOW+timedelta(minutes=1))
        with patch.object(KI,'fetch_opportunity_spread',side_effect=AssertionError('repeated quote')):
            review.prepare(KI,restarted,'later',selected,NOW+timedelta(minutes=15))
        self.assertEqual(len(self.rows('analysis_jobs')),2)

    def test_old_and_early_messages_are_suppressed_in_final_mode(self):
        batch,_=self.prepare(1)
        event=self.rows('events')[0]
        with self.store.transaction() as c:
            for kind in ('EARLY_MOVEMENT','ANALYSIS'):
                c.execute('INSERT INTO outbox(id,event_id,kind,message,status,created_at) VALUES(?,?,?,?,?,?)',
                    (kind,event['id'],kind,'old','PENDING',NOW.isoformat()))
        self.assertIsNone(KI.claim_delivery(self.store,now=NOW))
        self.assertTrue(all(r['status']=='FILTERED' for r in self.rows('outbox')))
        snap=KI.load_payload(event['payload'])['snapshot']
        self.assertFalse(KI.queue_early_movement(self.store,snap,NOW))

    def test_digest_revalidates_prices_direction_session_and_membership(self):
        self.prepare(1);self.finish_members();review.finalize(KI,self.store,NOW)
        ev=KI.load_payload(self.rows('events')[-1]['payload'])
        self.assertTrue(review.delivery_valid(KI,self.store,ev,NOW))
        self.assertFalse(review.delivery_valid(KI,self.store,ev,NOW+timedelta(minutes=16)))
        self.store.save_section('tickers',[])
        self.assertFalse(review.delivery_valid(KI,self.store,ev,NOW))
        self.assertIsNone(KI.claim_delivery(self.store,now=NOW))
        self.assertEqual(self.rows('outbox')[0]['status'],'FILTERED')

    def test_invalid_attention_cannot_pass_publication_and_raw_result_is_kept(self):
        self.prepare(1);job=self.rows('analysis_jobs')[0];ev=KI.load_payload(self.rows('events')[0]['payload'])
        ctx={'sources':[]};ctx['analysis_manifest']=KI.build_analysis_manifest(ev,ctx)
        bad=self.answer();bad['final_review']['explanation']='Gwarantowany wzrost i bezpieczna transakcja.'
        clean=KI.validate_event_analysis(bad,ev['snapshot'],ctx)
        self.assertTrue(KI.analysis_publication_issues(clean,True))
        self.assertTrue(any('decision:' in s for s in clean['quality_issues']))
        self.assertEqual(KI.validate_event_analysis(clean,ev['snapshot'],ctx),clean)

    def test_each_model_request_contains_only_own_issuer_and_full_manifest(self):
        self.prepare(2)
        for row in self.rows('events'):
            ev=KI.load_payload(row['payload']);s=ev['snapshot'];ctx={'sources':[],'cutoff':s['acquired_at']}
            ctx['analysis_manifest']=KI.build_analysis_manifest(ev,ctx)
            ctx['ai_preflight']=KI.automatic_ai_preflight(ev,ctx)
            self.assertTrue(ctx['ai_preflight']['allowed'])
            request=KI.event_analysis_request(ev,ctx)
            payload=json.loads(request['messages'][1]['content'])
            self.assertEqual(payload['proved_event']['snapshot']['ticker'],s['ticker'])
            background=payload['proved_event']['analysis_manifest']['company_background']
            self.assertEqual(background['ticker'],s['ticker'])
            self.assertIn('daily_history',background)
            schema=request['response_format']['json_schema']['schema']
            self.assertIn('final_review',schema['required'])
            self.assertIn('nie porównuj jej z innymi',request['messages'][0]['content'])

    def test_actual_analysis_pipeline_uses_one_model_call_per_company_not_second_sieve(self):
        self.prepare(1)
        with self.store.transaction() as c:
            job=c.execute('SELECT * FROM analysis_jobs').fetchone()
            ev=KI.load_payload(c.execute('SELECT payload FROM events WHERE id=?',(job['event_id'],)).fetchone()[0])
            ctx={'sources':[],'cutoff':ev['snapshot']['acquired_at']}
            c.execute("UPDATE analysis_jobs SET state='PENDING_AI',context=?",(KI.json_text(ctx),))
        response={'choices':[{'finish_reason':'stop','message':{'content':json.dumps(self.answer())}}],
                  'model':'mock','usage':{'total_tokens':1}}
        with patch.object(KI,'service_http',side_effect=model_transport(response)) as transport:
            self.assertTrue(KI.process_analysis_once(self.store,{'OPENAI_API_KEY':'fake'}))
            transport.assert_called_once()
            self.assertEqual(transport.call_args.args[0],'OpenAI')
        self.assertEqual(self.rows('analysis_jobs')[0]['state'],'DONE')
        self.assertEqual(self.rows('outbox'),[])
        review.finalize(KI,self.store,NOW)
        self.assertEqual(len(self.rows('outbox')),1)

    def test_open_batch_waits_for_all_jobs_or_deadline_without_repeating_calls(self):
        self.prepare(2)
        self.assertFalse(review.finalize(KI,self.store,NOW))
        self.assertTrue(review.finalize(KI,self.store,NOW+timedelta(minutes=13)))
        self.assertEqual(self.rows('company_review_batches')[0]['state'],'EMPTY')
        self.assertIsNone(KI.claim_analysis(self.store,now=NOW+timedelta(minutes=13)))
        self.assertTrue(all(r['state']=='FILTERED' for r in self.rows('analysis_jobs')))

    def test_uncertain_digest_delivery_is_not_replayed(self):
        self.prepare(1);self.finish_members();review.finalize(KI,self.store,NOW)
        KI.claim_delivery(self.store,now=NOW)
        KI.recover_service_jobs(self.store,'telegram')
        self.assertEqual(self.rows('outbox')[0]['status'],'UNCERTAIN')
        self.assertIsNone(KI.claim_delivery(self.store,now=NOW))

    def test_one_bad_report_does_not_block_other_valid_independent_company(self):
        self.prepare(2);self.finish_members()
        with self.store.transaction() as c:
            c.execute("UPDATE analysis_jobs SET result='{}' WHERE event_id=(SELECT event_id FROM analysis_jobs LIMIT 1)")
        self.assertTrue(review.finalize(KI,self.store,NOW))
        payload=KI.load_payload(self.rows('company_review_batches')[0]['payload'])
        self.assertEqual(len(payload['included']),1)
        self.assertEqual({r['status'] for r in payload['decisions']},{'INFORM','INVALID_REVIEW'})

    def test_full_report_view_is_read_only_and_has_own_sections(self):
        from streamlit.testing.v1 import AppTest
        self.prepare(1);self.finish_members();review.finalize(KI,self.store,NOW)
        code='import KI\nfrom pathlib import Path\nKI.render_growth_ranking(KI.Store(Path('+repr(str(self.store.path))+')))'
        with patch.object(KI,'service_http',side_effect=AssertionError('UI network')):
            app=AppTest.from_string(code).run(timeout=20)
        self.assertFalse(app.exception,list(app.exception))
        labels=[x.value for x in app.markdown]
        for title in ('Ruch i technika','Wolumen i aktywność','Ryzyko i ograniczenia','Źródła i kontekst','Wszystkie wskaźniki'):
            self.assertTrue(any(title in value for value in labels),title)

    def test_final_explanation_cannot_invent_reward_risk_from_unavailable_plan(self):
        self.prepare(1);row=self.rows('events')[0];ev=KI.load_payload(row['payload'])
        ctx={'sources':[]};ctx['analysis_manifest']=KI.build_analysis_manifest(ev,ctx)
        bad=self.answer();bad['final_review']['explanation']='Korzystna relacja zysku do ryzyka uzasadnia obserwację tej spółki.'
        clean=KI.validate_event_analysis(bad,ev['snapshot'],ctx)
        self.assertTrue(KI.analysis_publication_issues(clean,True))

    def test_telegram_disabled_keeps_complete_analysis_in_panel_without_delivery(self):
        settings=self.store.load_section('settings',{});settings['telegram_enabled']=False
        self.store.save_section('settings',settings)
        self.prepare(1);self.finish_members()
        self.assertTrue(review.finalize(KI,self.store,NOW))
        self.assertEqual(self.rows('analysis_jobs')[0]['state'],'DONE')
        self.assertEqual(self.rows('outbox')[0]['status'],'FILTERED')

    def test_mixed_local_material_is_not_sent_to_paid_research(self):
        selected=self.candidates(1)
        s=selected[0]['rank']['snapshot'];s['indicators']['last_macd_hist']=-.1
        with patch.object(KI,'fetch_opportunity_spread',side_effect=AssertionError('unnecessary quote')):
            review.prepare(KI,self.store,'cycle',selected,NOW)
        self.assertEqual(self.rows('analysis_jobs'),[])
        self.assertEqual(self.rows('research_requests'),[])
        payload=KI.load_payload(self.rows('company_review_batches')[0]['payload'])
        self.assertEqual(payload['pool'][0]['state'],'MIXED')

    def test_real_scanner_cycle_uses_final_route_and_respects_six_company_cap(self):
        self.candidates(9);at=NOW+timedelta(minutes=15)
        with self.store.transaction() as c:c.execute("UPDATE opportunities SET state='CONFIRMED' WHERE state='RESERVED'")
        class Clock(datetime):
            @classmethod
            def now(cls,tz=None):return at if tz else at.replace(tzinfo=None)
        def fetch(store,ticker):
            with store.connection() as c:
                row=c.execute('SELECT payload FROM observations WHERE ticker=? ORDER BY id DESC LIMIT 1',(ticker,)).fetchone()
            s=KI.load_payload(row[0]);s.pop('price_matrix',None)
            s['acquired_at']=at.isoformat();s['volume']+=1000
            s['chart_history'][-1]['volume']=s['volume']
            return s
        with ExitStack() as stack:
            stack.enter_context(patch.object(KI,'datetime',Clock))
            stack.enter_context(patch.object(KI,'fetch_automatic_snapshot',side_effect=fetch))
            quote=stack.enter_context(patch.object(KI,'fetch_opportunity_spread',return_value={}))
            stack.enter_context(patch.object(KI,'service_http',side_effect=AssertionError('HTTP in cycle')))
            for name in ('maintain_signal_history','daily_report_send','us_report_send','portfolio_check_alerts'):
                stack.enter_context(patch.object(KI,name))
            with redirect_stdout(io.StringIO()):cycle=KI.run_market_cycle(self.store)
        self.assertEqual(cycle['status'],'OK')
        self.assertEqual(quote.call_count,6)
        self.assertEqual(len(self.rows('analysis_jobs')),6)
        self.assertEqual(self.rows('outbox'),[])

    def test_digest_uses_existing_telegram_receipt_path_with_mock_transport(self):
        self.prepare(3);self.finish_members();review.finalize(KI,self.store,NOW)
        reply={'ok':True,'result':{'message_id':123,'chat':{'id':456}}}
        with patch.object(KI,'service_http',return_value=reply) as transport:
            self.assertTrue(KI.process_delivery_once(self.store,{'TELEGRAM_BOT_TOKEN':'fake','TELEGRAM_CHAT_ID':'456'}))
            transport.assert_called_once()
            self.assertEqual(transport.call_args.args[0],'Telegram')
            self.assertIn('KOŃCOWE OCENY SPÓŁEK',transport.call_args.kwargs['payload']['text'])
        self.assertEqual(self.rows('outbox')[0]['status'],'DELIVERED')
        self.assertEqual(len(self.rows('delivery_receipts')),1)

    def test_setting_activation_and_restore_preserve_all_other_preferences(self):
        import configure_final_reviews as config
        settings=self.store.load_section('settings',{});settings.pop(review.SETTING)
        settings['custom_preference']='keep'
        self.store.save_section('settings',settings)
        root=Path(self.tmp.name)
        shutil.copy2(Path(KI.__file__).with_name('final_company_review.py'),root/'final_company_review.py')
        with patch.object(config,'ROOT',root):
            before=config.change(self.store.path,'read')
            self.assertFalse(before['present'])
            config.change(self.store.path,'enable')
            self.assertTrue(self.store.load_section('settings',{})[review.SETTING])
            config.change(self.store.path,'restore',before)
        self.assertEqual(self.store.load_section('settings',{}),settings)
        with self.store.connection() as c:
            self.assertIsNone(c.execute('SELECT payload FROM settings WHERE key=?',(review.SETTING,)).fetchone())

    def test_generic_one_sentence_is_not_a_complete_final_company_review(self):
        self.prepare(1);row=self.rows('events')[0];ev=KI.load_payload(row['payload'])
        ctx={'sources':[]};ctx['analysis_manifest']=KI.build_analysis_manifest(ev,ctx)
        answer=self.answer();answer['assessment']['movement']='Wzrost jest zgodny ze wskazaniami.'
        clean=KI.validate_event_analysis(answer,ev['snapshot'],ctx)
        self.assertTrue(KI.analysis_publication_issues(clean,True))

    def test_final_review_heading_and_waiting_state_are_visible_without_any_batch(self):
        from streamlit.testing.v1 import AppTest
        code='import KI\nfrom pathlib import Path\nimport final_company_review as review\nreview.render(KI,KI.Store(Path('+repr(str(self.store.path))+')))'
        with patch.object(KI,'service_http',side_effect=AssertionError('UI network')):
            app=AppTest.from_string(code).run(timeout=20)
        self.assertFalse(app.exception,list(app.exception))
        self.assertIn('Końcowe oceny spółek',[x.value for x in app.subheader])
        self.assertTrue(any('Oczekuje na pierwsze' in x.value for x in app.info))
        with self.store.connection() as c:self.assertFalse(review.exists(c))

    def test_retained_streamlit_callback_uses_own_globals_after_main_module_replacement(self):
        self.prepare(1);self.finish_members();review.finalize(KI,self.store,NOW)
        namespace=dict(KI.__dict__)
        namespace['__name__']='__main__'
        exec(compile('def retained(store):\n    return company_review.render(company_review.script_api(globals()),store)',
                     '<retained Streamlit fragment>','exec'),namespace)
        from streamlit.testing.v1 import AppTest
        # Keep a real callback from its old script namespace; replace the module
        # registry with a fresh script module lacking KI's functions.
        callback=namespace['retained']
        empty=types.ModuleType('__main__')
        self.assertFalse(hasattr(empty,'load_payload'))
        with patch.dict(sys.modules,{'__main__':empty}):
            api=review.script_api(callback.__globals__)
            self.assertIs(api.load_payload,KI.load_payload)
            self.assertIs(api.render_technical_events,KI.render_technical_events)
            self.assertTrue(review.due(self.store) is False)
        code='''import KI
import final_company_review as review
from pathlib import Path
import sys,types
namespace=dict(KI.__dict__)
namespace['__name__']='__main__'
exec('def retained(store):\\n    return company_review.render(company_review.script_api(globals()),store)',namespace)
old=sys.modules.get('__main__')
try:
    sys.modules['__main__']=types.ModuleType('__main__')
    namespace['retained'](KI.Store(Path('''+repr(str(self.store.path))+''')))
finally:
    if old is not None:sys.modules['__main__']=old
'''
        app=AppTest.from_string(code).run(timeout=20)
        self.assertFalse(app.exception,list(app.exception))
        self.assertIn('Końcowe oceny spółek',[x.value for x in app.subheader])

    def test_new_final_review_has_own_id_and_never_overwrites_previous_done_report(self):
        selected=self.candidates(2);old_reports={}
        with self.store.transaction() as c:
            for row in selected:
                seq=row['sequence_id'];payload=KI.json_text({'kind':'CONFIRMED_OPPORTUNITY','snapshot':row['rank']['snapshot']})
                result=KI.json_text({'analysis':{'legacy_report':'Zachowaj cały raport'},'provider':{'usage':{'total_tokens':50}}})
                c.execute('INSERT INTO events VALUES(?,?,?,?,?)',(seq,row['ticker'],'1h',(NOW-timedelta(hours=5)).isoformat(),payload))
                c.execute('INSERT INTO analysis_jobs(event_id,state,context,result,attempts,updated_at) VALUES(?,?,?,?,?,?)',
                          (seq,'DONE','{}',result,2,(NOW-timedelta(hours=5)).isoformat()))
                old_reports[seq]=(payload,result)
        with patch.object(KI,'fetch_opportunity_spread',return_value={}):
            batch=review.prepare(KI,self.store,'cycle',selected,NOW)
        payload=KI.load_payload(self.rows('company_review_batches')[0]['payload'])
        self.assertEqual(len(payload['members']),2);self.assertFalse(payload['diagnostics'])
        with self.store.connection() as c:
            for row in selected:
                seq=row['sequence_id'];new_id=review.event_id_for(seq,batch)
                self.assertNotEqual(seq,new_id);self.assertIn(new_id,payload['members'])
                old=c.execute('SELECT * FROM analysis_jobs WHERE event_id=?',(seq,)).fetchone()
                self.assertEqual((old['state'],old['attempts'],old['result']),('DONE',2,old_reports[seq][1]))
                self.assertEqual(c.execute('SELECT payload FROM events WHERE id=?',(seq,)).fetchone()[0],old_reports[seq][0])
                new=c.execute('SELECT * FROM analysis_jobs WHERE event_id=?',(new_id,)).fetchone()
                self.assertEqual(new['state'],'PENDING_CONTEXT');self.assertEqual(new['attempts'],0)
                saved=KI.load_payload(c.execute('SELECT payload FROM opportunities WHERE sequence_id=?',(seq,)).fetchone()[0])
                self.assertEqual(saved['last_analysis_event_id'],new_id)
        claimed=KI.claim_analysis(self.store,now=NOW)
        self.assertIn(claimed['event_id'],payload['members'])
        self.assertNotIn(claimed['event_id'],old_reports)

    def test_only_unstarted_integrity_failures_release_reservations_without_provider_replay(self):
        self.prepare(2)
        with self.store.transaction() as c:
            batch=c.execute('SELECT * FROM company_review_batches').fetchone();p=KI.load_payload(batch['payload'])
            diagnostics=[{'event_id':r['event_id'],'status':'PREPARATION_FAILED','error_type':'IntegrityError'} for r in c.execute('SELECT * FROM company_review_seen')]
            p.update(members=[],diagnostics=diagnostics)
            c.execute("UPDATE company_review_batches SET state='EMPTY',payload=?",(KI.json_text(p),))
            # Keep one real batch event: it must make its reservation ineligible
            # for release even if a stale diagnostic incorrectly says otherwise.
            members=[r['event_id'] for r in c.execute('SELECT * FROM company_review_seen')]
            c.execute('DELETE FROM analysis_jobs WHERE event_id=?',(members[0],))
            c.execute('DELETE FROM events WHERE id=?',(members[0],))
            review.release_unstarted(KI,c,NOW)
        seen=self.rows('company_review_seen')
        self.assertEqual(len(seen),1);self.assertEqual(seen[0]['event_id'],members[1])
        self.assertEqual(len(self.rows('analysis_jobs')),1)
        self.assertEqual(self.rows('research_requests'),[])
        p=KI.load_payload(self.rows('company_review_batches')[0]['payload'])
        self.assertEqual(p['recovery'][0]['status'],'UNSTARTED_RESERVATION_RELEASED')

    def test_new_review_link_survives_next_matrix_refresh_and_uses_new_job_timestamp(self):
        self.prepare(1);self.finish_members()
        row=self.rows('events')[0];ev=KI.load_payload(row['payload']);s=copy.deepcopy(ev['snapshot'])
        seq=ev['sequence_id'];s['acquired_at']=(NOW+timedelta(minutes=15)).isoformat()
        s['price_matrix']['last_acquired_at']=s['acquired_at']
        with self.store.transaction() as c:
            c.execute('INSERT INTO events VALUES(?,?,?,?,?)',(seq,s['ticker'],'1h',(NOW-timedelta(hours=5)).isoformat(),KI.json_text({'snapshot':s})))
            c.execute('INSERT INTO analysis_jobs(event_id,state,updated_at) SELECT ?,?,? WHERE NOT EXISTS(SELECT 1 FROM analysis_jobs WHERE event_id=?)',
                      (seq,'DONE',(NOW-timedelta(hours=5)).isoformat(),seq))
        updated=KI.record_opportunity(self.store,s,'refresh',NOW+timedelta(minutes=15))
        self.assertEqual(updated['state'],'SELECTED')
        stored=KI.load_payload(self.rows('opportunities')[0]['payload'])
        self.assertEqual(stored['last_analysis_event_id'],row['id'])


if __name__=='__main__':unittest.main()
