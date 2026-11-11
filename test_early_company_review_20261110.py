"""Preliminary-to-AI-to-one-digest on real temporary SQLite, providers mocked."""
from contextlib import ExitStack,redirect_stdout
from datetime import datetime,timedelta,timezone
from pathlib import Path
import copy,io,json,tempfile,unittest
from unittest.mock import patch

import KI
import early_company_review as early
import final_company_review as review
import ki2_ops_guard
import selected_opportunities
from test_final_company_review_20261106 import model_transport


class EarlyCompanyReviewTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
        self.store=KI.Store(Path(tmp.name)/'early-final.sqlite3')
        self.now=datetime(2026,11,10,14,30,tzinfo=timezone.utc)
        self.opening=self.now;owner=self
        class Clock(datetime):
            @classmethod
            def now(cls,tz=None):return owner.now if tz else owner.now.replace(tzinfo=None)
        self.stack=ExitStack();self.addCleanup(self.stack.close)
        self.stack.enter_context(redirect_stdout(io.StringIO()))
        self.stack.enter_context(patch.object(KI,'datetime',Clock))
        self.stack.enter_context(patch.object(ki2_ops_guard,'LOCK_PATH',Path(tmp.name)/'test.lock'))
        self.settings={'pipeline_enabled':True,'telegram_enabled':True,'price_threshold_pct':2.,
                       'auto_scan_interval':15,review.SETTING:True}
        self.store.save_section('settings',self.settings);self.store.save_section('tickers',['HUMA'])
        KI._save_daily_history(self.store,'HUMA',[{'session_date':'2026-11-09','status':'CLOSED',
            'open':.455,'high':.455,'low':.455,'close':.455,'volume':1000000}],self.now)

    def rows(self,table):
        with self.store.connection() as c:return [dict(r) for r in c.execute('SELECT * FROM '+table)]

    def snapshot(self,minutes,price=.549,volume=2639351.,opening=.4501):
        at=self.opening+timedelta(minutes=minutes)
        start=self.opening+timedelta(hours=int(minutes//60));end=start+timedelta(hours=1)
        s=KI.opportunity_test_snapshot(at,'HUMA',price)
        s.update(currency='USD',volume=volume,average_volume=759102.,rvol=volume/759102.,
            candle_time=start.isoformat(),candle_end=end.isoformat(),candle_status='OPEN',
            ohlc={'open':opening,'high':max(price,opening)+.0001,'low':min(price,opening)-.0001,'close':price},
            indicators={'ma_fast':.45,'ma_slow':.44,'last_macd_hist':.01,'rsi':60.,'adx':25.,'plus_di':30.,'minus_di':10.},
            previous_closed={'time':(self.opening-timedelta(hours=18)).isoformat(),
                'end':(self.opening-timedelta(hours=17)).isoformat(),'status':'CLOSED',
                'open':.455,'high':.456,'low':.454,'close':.455,'volume':1000000.,'rvol':2.})
        history=[];bar=self.opening
        while bar<start:
            history.append({'time':bar.isoformat(),'end':(bar+timedelta(hours=1)).isoformat(),
                'status':'CLOSED','open':opening,'high':max(price,opening)+.0001,
                'low':min(price,opening)-.0001,'close':price,'volume':6504423.})
            bar+=timedelta(hours=1)
        if history:s['previous_closed']={**history[-1],'rvol':8.56}
        s['chart_history']=history+[{**s['ohlc'],'time':start.isoformat(),'end':end.isoformat(),
                                    'status':'OPEN','volume':volume}]
        return s

    def read(self,minutes,price=.549,volume=2639351.,opening=.4501,cycle='cycle'):
        s=self.snapshot(minutes,price,volume,opening);self.now=KI.parse_market_time(s['acquired_at'])
        result=KI.detect_market(self.store,s,{**self.settings,'price_matrix_enabled':True})
        s={**s,'price_matrix':result['price_matrix']}
        KI.record_opportunity(self.store,s,cycle,self.now)
        return s

    def candidate(self,opening=.4501):
        self.read(0,opening,801675.,opening)
        return self.read(15,.549,2639351.,opening)

    def prepare(self,snapshot=None):
        s=snapshot or self.candidate()
        chosen=early.reserve(KI,self.store,'cycle',self.now)
        self.assertEqual(len(chosen['selected']),1,chosen)
        with patch.object(KI,'fetch_opportunity_spread',return_value={}) as quote:
            batch=review.prepare(KI,self.store,'cycle',chosen['selected'],self.now,early_pool=chosen['pool'])
        self.assertEqual(quote.call_count,1)
        return batch,s

    def run_ai(self,attention='INFORM'):
        with self.store.transaction() as c:
            ev=KI.load_payload(c.execute('SELECT payload FROM events').fetchone()[0])
            ctx={'sources':[],'cutoff':ev['snapshot']['acquired_at']}
            c.execute("UPDATE analysis_jobs SET state='PENDING_AI',context=?",(KI.json_text(ctx),))
        response={'choices':[{'finish_reason':'stop','message':{'content':json.dumps({'final_review':{'attention':attention}})}}],
                  'usage':{'total_tokens':1},'model':'mock'}
        with patch.object(KI,'service_http',side_effect=model_transport(response)) as model:
            self.assertTrue(KI.process_analysis_once(self.store,{'OPENAI_API_KEY':'fake'}))
        self.assertEqual(model.call_count,1)
        self.assertEqual(self.rows('analysis_jobs')[0]['state'],'DONE',self.rows('analysis_jobs')[0]['last_error'])
        return ev

    def test_first_strong_candidate_gets_one_ai_review_top5_and_one_digest_without_fake_confirmation(self):
        batch,s=self.prepare();ev=self.run_ai()
        self.assertTrue(early.is_event(ev));self.assertEqual(s['price_matrix']['consecutive_reads'],1)
        self.assertFalse(KI.telegram_movement_confirmed(ev,self.now))
        self.assertEqual(self.rows('signal_confirmations'),[])
        result=KI.load_payload(self.rows('analysis_jobs')[0]['result'])['analysis']
        self.assertIn('wstępny',result['assessment']['movement'])
        self.assertIn('nie została zakończona',result['assessment']['movement'])
        self.assertNotIn('Potwierdzono ruch',result['assessment']['movement'])
        self.assertEqual(self.rows('outbox'),[])
        self.assertTrue(review.finalize(KI,self.store,self.now));self.assertFalse(review.finalize(KI,self.store,self.now))
        out=self.rows('outbox');self.assertEqual(len(out),1);self.assertEqual(out[0]['kind'],'FINAL_COMPANY_DIGEST')
        self.assertIn('WSTĘPNA OCENA',out[0]['message']);self.assertIn('1/3',out[0]['message'])
        view=selected_opportunities.collect(KI,self.store,self.now)
        self.assertEqual(view['cards'],[])
        cards=view['rising_watch'];self.assertEqual(len(cards),1)
        html=selected_opportunities.cards_html(KI,cards,self.now)
        self.assertIn('WSTĘPNA OCENA',html);self.assertIn('1/3',html)
        with patch.object(KI,'service_http',return_value={'ok':True,'result':{'message_id':123,'chat':{'id':456}}}) as telegram:
            self.assertTrue(KI.process_delivery_once(self.store,{'TELEGRAM_BOT_TOKEN':'fake','TELEGRAM_CHAT_ID':'456'}))
        telegram.assert_called_once();self.assertEqual(self.rows('outbox')[0]['status'],'DELIVERED')

    def test_huma_measured_price_volume_gap_keeps_one_proof_but_allows_preliminary_assessment(self):
        # Real supplied prices/volumes; the coherent OHLC fixture is synthetic.
        self.candidate();s=self.read(45,.58280998468399,6504423.)
        self.assertEqual(s['price_matrix']['consecutive_reads'],1)
        self.assertAlmostEqual(s['price_matrix']['change_pct'],28.0901065,places=4)
        batch,s=self.prepare(s);self.assertTrue(batch)
        self.assertEqual(self.rows('signal_confirmations'),[])
        self.assertEqual(KI.load_payload(self.rows('events')[0]['payload'])['confirmation']['observed_reads'],1)

    def test_new_candle_zero_volume_does_not_reuse_old_volume_or_call_provider(self):
        self.candidate();self.read(45,.58281,6504423.);s=self.read(60,.5819,0.)
        chosen=early.reserve(KI,self.store,'cycle',self.now)
        self.assertEqual(chosen['selected'],[]);self.assertEqual(len(chosen['pool']),1)
        with patch.object(KI,'fetch_opportunity_spread',side_effect=AssertionError('provider')):
            review.prepare(KI,self.store,'cycle',[],self.now,early_pool=chosen['pool'])
        self.assertEqual(self.rows('events'),[])

    def test_stale_carried_missing_base_missing_activity_and_low_rvol_are_rejected(self):
        good=self.candidate()
        cases=[{'volume':0.},{'rvol':1.49},{'latest_price_origin':'carried_previous_close'},
               {'ohlc':{**good['ohlc'],'high':.1}},
               {'price_matrix':{**good['price_matrix'],'reference_status':'MISSING_PREVIOUS_SESSION'}},
               {'price_matrix':{**good['price_matrix'],'activity_evidence':'NO_NEW_ACTIVITY'}},
               {'price_matrix':{**good['price_matrix'],'change_pct':1.}},
               {'price_matrix':{**good['price_matrix'],'last_activity_at':self.opening.isoformat()}},
               {'currency':'PLN'},{'indicators':{} }]
        for change in cases:
            with self.subTest(change=change):self.assertFalse(early.gate(KI,{**good,**change},self.now,self.settings)['allowed'])
        self.assertFalse(early.gate(KI,good,self.now+timedelta(minutes=16),self.settings)['allowed'])

    def test_missing_session_bar_blocks_selection_with_visible_reason(self):
        self.candidate();s=self.read(75,.58,7000000.)
        bad=copy.deepcopy(s);bad['chart_history']=[bad['chart_history'][-1]]
        self.assertFalse(early.gate(KI,bad,self.now,self.settings)['allowed'])

    def test_local_adverse_retrace_blocks_preliminary_before_any_quote_or_ai(self):
        s=self.candidate();bad=copy.deepcopy(s);bad['ohlc']['high']=.70
        bad['chart_history'][-1]['high']=.70
        with self.store.transaction() as c:
            c.execute('UPDATE observations SET payload=? WHERE ticker=? AND acquired_at=?',(KI.json_text(bad),'HUMA',bad['acquired_at']))
            row=c.execute("SELECT * FROM opportunities WHERE ticker='HUMA'").fetchone()
            rank=KI.load_payload(row['payload']);rank['snapshot']=bad
            c.execute('UPDATE opportunities SET payload=?',(KI.json_text(rank),))
        chosen=early.reserve(KI,self.store,'cycle',self.now)
        with patch.object(KI,'fetch_opportunity_spread',side_effect=AssertionError('provider')):
            review.prepare(KI,self.store,'cycle',chosen['selected'],self.now)
        self.assertEqual(self.rows('analysis_jobs'),[])
        self.assertEqual(self.rows('opportunities')[0]['state'],'CANDIDATE')

    def test_specific_ai_panel_decision_does_not_create_a_notification(self):
        s=self.candidate(opening=.55);self.prepare(s);self.run_ai('PANEL_ONLY')
        self.assertTrue(review.finalize(KI,self.store,self.now));self.assertEqual(self.rows('outbox'),[])
        self.assertEqual(selected_opportunities.collect(KI,self.store,self.now)['cards'],[])

    def test_same_slot_and_unchanged_followup_do_not_duplicate_jobs_or_promote_candidate(self):
        batch,s=self.prepare();self.run_ai()
        self.assertIsNone(review.prepare(KI,self.store,'cycle',[],self.now))
        self.read(30,.549,3500000.)
        self.assertEqual(len(self.rows('analysis_jobs')),1)
        self.assertEqual(self.rows('opportunities')[0]['state'],'SELECTED')

    def test_three_real_proofs_can_upgrade_preliminary_with_new_event_without_rewriting_old(self):
        batch,s=self.prepare();ev=self.run_ai()
        self.read(30,.549,3500000.);latest=self.read(45,.549,4500000.)
        self.assertEqual(latest['price_matrix']['consecutive_reads'],3)
        self.assertEqual(len(self.rows('signal_confirmations')),1)
        chosen=KI.reserve_opportunities(self.store,'cycle',self.now)
        self.assertEqual(len(chosen),1)
        with patch.object(KI,'fetch_opportunity_spread',return_value={}):
            review.prepare(KI,self.store,'cycle',chosen,self.now)
        self.assertEqual(len(self.rows('analysis_jobs')),2)
        with self.store.connection() as c:
            old=KI.load_payload(c.execute('SELECT payload FROM events WHERE id=?',(self.rows('analysis_jobs')[0]['event_id'],)).fetchone()[0])
        self.assertEqual(old['snapshot'],ev['snapshot']);self.assertTrue(early.is_event(old))

    def test_latest_zero_volume_or_new_pending_report_hides_previous_positive_top5(self):
        self.prepare();self.run_ai();review.finalize(KI,self.store,self.now)
        self.assertEqual(len(selected_opportunities.collect(KI,self.store,self.now)['rising_watch']),1)
        self.read(30,.549,0.)
        self.assertEqual(selected_opportunities.collect(KI,self.store,self.now)['cards'],[])
        self.assertIsNone(KI.claim_delivery(self.store,now=self.now))

    def test_scanner_reaches_preliminary_queue_without_three_read_reservation(self):
        self.read(0,.4501,801675.);snapshot=self.snapshot(15);self.now=self.opening+timedelta(minutes=15)
        with ExitStack() as stack:
            stack.enter_context(patch.object(KI,'fetch_automatic_snapshot',return_value=snapshot))
            quote=stack.enter_context(patch.object(KI,'fetch_opportunity_spread',return_value={}))
            for name in ('portfolio_check_alerts','daily_report_send','us_report_send','maintain_signal_history'):
                stack.enter_context(patch.object(KI,name))
            KI.run_market_cycle(self.store)
        self.assertEqual(quote.call_count,1)
        self.assertEqual(len(self.rows('analysis_jobs')),1)
        self.assertTrue(early.is_event(KI.load_payload(self.rows('events')[0]['payload'])))
        self.assertEqual(self.rows('signal_confirmations'),[])

    def test_preliminary_cannot_be_forged_into_standalone_or_confirmed_delivery(self):
        batch,s=self.prepare();ev=KI.load_payload(self.rows('events')[0]['payload'])
        self.assertFalse(KI.telegram_movement_confirmed(ev,self.now))
        for change in ({'company_review_batch':None},{'review_stage':None},{'kind':'CONFIRMED_OPPORTUNITY'}):
            self.assertFalse(KI.opportunity_delivery_valid(self.store,{**ev,**change},self.now))

    def test_prepare_failure_keeps_candidate_state_and_never_creates_confirmation(self):
        self.candidate();chosen=early.reserve(KI,self.store,'cycle',self.now)
        with patch.object(KI,'fetch_opportunity_spread',side_effect=RuntimeError('fixture unavailable')):
            review.prepare(KI,self.store,'cycle',chosen['selected'],self.now)
        self.assertEqual(self.rows('opportunities')[0]['state'],'CANDIDATE')
        self.assertEqual(self.rows('analysis_jobs'),[]);self.assertEqual(self.rows('signal_confirmations'),[])

    def test_current_threshold_change_or_removal_prevents_preliminary_delivery(self):
        self.prepare();ev=self.run_ai();review.finalize(KI,self.store,self.now)
        self.store.save_section('settings',{**self.settings,'price_threshold_pct':30.})
        self.assertFalse(KI.opportunity_delivery_valid(self.store,ev,self.now))
        self.store.save_section('settings',self.settings);self.store.save_section('tickers',[])
        self.assertFalse(KI.opportunity_delivery_valid(self.store,ev,self.now))

    def test_preliminary_validator_refuses_a_report_without_explicit_stage(self):
        self.prepare();self.run_ai();row=self.rows('analysis_jobs')[0]
        ctx=KI.load_payload(row['context']);analysis=KI.load_payload(row['result'])['analysis']
        analysis['assessment']['movement']='Potwierdzono ruch od bazy. Przebieg sesji wskazuje na zgodność z techniką.'
        self.assertTrue(review.validate_final(analysis,ctx['analysis_manifest'],lambda text:False))

    def test_six_preliminary_labels_and_full_capped_summaries_fit_one_telegram(self):
        self.prepare();self.run_ai()
        with self.store.connection() as c:
            items=review.records(KI,c,[self.rows('analysis_jobs')[0]['event_id']])
        copies=[]
        for i in range(6):
            item=copy.deepcopy(items[0]);ev=KI.load_payload(item['payload']);ctx=KI.load_payload(item['context'])
            result=KI.load_payload(item['result']);ev['snapshot']['ticker']='LONGTICK'+str(i)
            ev['snapshot']['price']=1000000.59
            result['analysis']['final_review']['explanation']='Uzasadnienie oraz ograniczenie oceny. '*20
            result['analysis']['assessment']['risk']='Jawne ograniczenie ryzyka i wykonania. '*20
            ctx['analysis_manifest']['trade_plan']={'status':'UNAVAILABLE','reason':'Brak kompletu danych do planu. '*20}
            item.update(payload=KI.json_text(ev),context=KI.json_text(ctx),result=KI.json_text(result));copies.append(item)
        text=review.digest_message(KI,copies,self.now.isoformat())
        self.assertLessEqual(len(text),3900);self.assertEqual(text.count('WSTĘPNA OCENA'),6)


class MixedLaneLimitTests(unittest.TestCase):
    def test_preliminary_and_confirmed_share_six_jobs_and_one_batch(self):
        from test_final_company_review_20261106 import FinalCompanyReviewTests,NOW
        f=FinalCompanyReviewTests();f.setUp();self.addCleanup(f.doCleanups)
        chosen=f.candidates(8)
        with f.store.transaction() as c:
            for row in chosen[2:]:
                snap=row['rank']['snapshot'];matrix=snap['price_matrix']
                matrix.update(state='CANDIDATE',consecutive_reads=1,activity_verified=False)
                row['review_stage']=early.STAGE
                c.execute('UPDATE opportunities SET payload=? WHERE sequence_id=?',(KI.json_text(row['rank']),row['sequence_id']))
                c.execute("UPDATE observations SET payload=? WHERE ticker=? AND acquired_at=?",(KI.json_text(snap),snap['ticker'],snap['acquired_at']))
        with patch.object(KI,'fetch_opportunity_spread',return_value={}) as quote:
            review.prepare(KI,f.store,'cycle',chosen,NOW)
        self.assertEqual(quote.call_count,6)
        self.assertEqual(len(f.rows('analysis_jobs')),6);self.assertEqual(len(f.rows('company_review_batches')),1)
        payload=KI.load_payload(f.rows('company_review_batches')[0]['payload'])
        self.assertEqual(sum(x['state']=='CYCLE_LIMIT' for x in payload['pool']),2)
        for row in f.rows('opportunities'):
            if row['sequence_id'] in {x['sequence_id'] for x in chosen[6:]}:self.assertEqual(row['state'],'CANDIDATE')


if __name__=='__main__':unittest.main()
