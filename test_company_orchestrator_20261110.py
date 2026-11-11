"""One decision policy across real fixture SQLite, AI, one digest and mobile UI."""
import copy,json,unittest
from datetime import timedelta
from unittest.mock import patch

import KI
import company_orchestrator as control
import selected_opportunities as top
import test_final_company_review_20261106 as fixtures

NOW=fixtures.NOW


class CompanyOrchestratorTests(unittest.TestCase):
    def sample(self,with_plan=False):
        f=fixtures.FinalCompanyReviewTests();f.setUp();self.addCleanup(f.doCleanups)
        rows=f.candidates(1,with_plan=with_plan)
        s=rows[0]['rank']['snapshot'];m=KI.build_analysis_manifest({'snapshot':s,'autonomous_assessment_version':1},{'sources':[]})
        return f,rows,s,m

    def assess(self,s,m,**kwargs):return control.assess(KI,s,m,{'price_threshold_pct':2.},kwargs.pop('now',NOW),**kwargs)

    def test_complete_real_plan_routes_up_to_top_but_does_not_make_execution_claim(self):
        f,rows,s,m=self.sample(True);decision=self.assess(s,m)
        self.assertTrue(decision['review_allowed']);self.assertEqual(decision['role'],control.TOP)
        self.assertTrue(control.plan_ready(KI,s,m['trade_plan'],NOW))
        self.assertNotEqual(m['local_review']['execution'],'TIMESTAMP_CONFIRMED')
        self.assertTrue(decision['limitations'])

    def test_up_without_plan_still_gets_ai_but_is_only_a_watch(self):
        f,rows,s,m=self.sample();decision=self.assess(s,m)
        self.assertTrue(decision['review_allowed']);self.assertEqual(decision['role'],control.WATCH)
        self.assertFalse(decision['plan_complete']);self.assertTrue(decision['connections']['plan']['reason'])

    def test_down_with_aligned_indicators_is_warning_and_never_long_top(self):
        f,rows,s,m=self.sample()
        s=copy.deepcopy(s);s.update(price=95.,ohlc={'open':100.,'high':100.1,'low':94.9,'close':95.})
        s['price_matrix'].update(last_price=95.,change_pct=-5.)
        s['indicators'].update(ma_fast=99.,rsi=40.,last_macd_hist=-.1,plus_di=10.,minus_di=30.)
        s['chart_history'][-1].update(s['ohlc'])
        m=KI.build_analysis_manifest({'snapshot':s,'autonomous_assessment_version':1},{'sources':[]})
        decision=self.assess(s,m)
        self.assertTrue(decision['review_allowed']);self.assertEqual(decision['role'],control.WARNING)
        self.assertEqual(decision['connections']['technical']['verdict'],'ALIGNED')
        self.assertFalse(decision['plan_complete'])

    def test_missing_reference_and_stale_data_have_specific_actions_and_next_conditions(self):
        f,rows,s,m=self.sample()
        bad=copy.deepcopy(s);bad['price_matrix']['reference_status']='MISSING_PREVIOUS_SESSION'
        decision=self.assess(bad,m)
        self.assertEqual(decision['action'],'WAIT_FOR_REFERENCE');self.assertFalse(decision['review_allowed'])
        self.assertTrue(decision['next_check'])
        late=self.assess(s,m,now=NOW+timedelta(minutes=16))
        self.assertEqual(late['action'],'WAIT_FOR_DATA');self.assertFalse(late['review_allowed'])

    def test_incomplete_session_and_measured_risk_stop_ai_with_preserved_evidence(self):
        f,rows,s,m=self.sample();bad=copy.deepcopy(s);bad['chart_history']=[]
        decision=self.assess(bad,m)
        self.assertEqual(decision['action'],'WAIT_FOR_SESSION_DATA')
        risk=copy.deepcopy(s);risk['ohlc']['high']=risk['price']*1.1
        risk['chart_history'][-1]['high']=risk['ohlc']['high']
        manifest=KI.build_analysis_manifest({'snapshot':risk,'autonomous_assessment_version':1},{'sources':[]})
        decision=self.assess(risk,manifest)
        self.assertEqual(decision['action'],'KEEP_IN_PANEL');self.assertEqual(decision['reason'],'RISK_DOMINANT')
        self.assertIn('ADVERSE_RETRACE',decision['connections']['technical']['decisive_reasons'])

    def test_price_policy_change_is_checked_without_resetting_old_confirmation(self):
        f,rows,s,m=self.sample()
        decision=control.assess(KI,s,m,{'price_threshold_pct':6.},NOW)
        self.assertEqual(decision['action'],'WAIT_FOR_MOVEMENT');self.assertFalse(decision['review_allowed'])
        self.assertEqual(s['price_matrix']['consecutive_reads'],3)

    def test_incomplete_foreign_stale_or_inconsistent_plan_cannot_fill_top(self):
        f,rows,s,m=self.sample(True)
        variants=[{'sl':s['price']+1},{'tp2':m['trade_plan']['tp1']},{'currency':'OTHER'},
                  {'as_of':(NOW+timedelta(minutes=1)).isoformat()}, {'rr1':99.},
                  {'resistances':[]},{'support':7.}, {'valid_until':NOW.isoformat()}]
        for change in variants:
            with self.subTest(change=change):
                modified=copy.deepcopy(m);modified['trade_plan'].update(change)
                self.assertEqual(self.assess(s,modified)['role'],control.WATCH)

    def test_read_only_assessment_keeps_frozen_inputs_and_ai_can_decline(self):
        f,rows,s,m=self.sample(True);before=copy.deepcopy((s,m))
        decision=self.assess(s,m);published=control.publish(decision,{'final_review':{'attention':'PANEL_ONLY'}})
        self.assertEqual((s,m),before);self.assertEqual(published['role'],control.PANEL)
        self.assertFalse(published['notify']);self.assertTrue(decision['review_allowed'])

    def test_unchanged_prior_assessment_waits_for_change_not_for_another_paid_call(self):
        f,rows,s,m=self.sample()
        decision=self.assess(s,m,previous={'allowed':False,'reason':'NO_MATERIAL_CHANGE','previous_event_id':'old'})
        self.assertEqual(decision['action'],'WAIT_FOR_CHANGE');self.assertFalse(decision['review_allowed'])
        self.assertEqual(decision['previous_assessment']['previous_event_id'],'old')

    def test_missing_data_takes_priority_over_an_old_cooldown(self):
        f,rows,s,m=self.sample();s=copy.deepcopy(s);s['volume']=0.
        decision=self.assess(s,m,previous={'allowed':False,'reason':'NO_MATERIAL_CHANGE'})
        self.assertEqual(decision['action'],'WAIT_FOR_DATA');self.assertTrue(decision['issues'])

    def test_latest_loss_of_plan_downgrades_to_watch_without_reinterpreting_frozen_ai(self):
        f,rows,s,m=self.sample(True)
        event={'snapshot':s,'kind':'CONFIRMED_OPPORTUNITY','company_review_batch':'fixture'}
        latest=copy.deepcopy(s);latest['indicators'].pop('atr')
        before=copy.deepcopy(m)
        decision=control.report_decision(KI,event,{'analysis_manifest':m},{'final_review':{'attention':'INFORM'}},{},NOW,latest)
        self.assertTrue(decision['notify']);self.assertEqual(decision['role'],control.WATCH)
        self.assertEqual(m,before)

    def test_old_completion_cannot_overwrite_newer_company_state(self):
        f,rows,s,m=self.sample();old=self.assess(s,m)
        newer=copy.deepcopy(old);newer.update(as_of=(NOW+timedelta(minutes=15)).isoformat(),action='WAIT_FOR_DATA')
        with f.store.transaction() as db:
            control.save(KI,db,newer);control.save(KI,db,old)
        with f.store.connection() as db:state=KI.load_payload(db.execute("SELECT payload FROM runtime WHERE key=?",('orchestrator:'+s['ticker'],)).fetchone()[0])
        self.assertEqual(state['action'],'WAIT_FOR_DATA');self.assertEqual(state['as_of'],newer['as_of'])

    def test_failed_provider_gets_a_control_state_without_retry_or_telegram(self):
        f,rows,s,m=self.sample()
        with patch.object(KI,'fetch_opportunity_spread',return_value={}):KI.company_review.prepare(KI,f.store,'cycle',rows,NOW)
        with f.store.transaction() as db:db.execute("UPDATE analysis_jobs SET state='FAILED',last_error='fixture' ")
        KI.company_review.finalize(KI,f.store,NOW)
        with f.store.connection() as db:decision=KI.load_payload(db.execute("SELECT payload FROM runtime WHERE key=?",('orchestrator:'+s['ticker'],)).fetchone()[0])
        self.assertEqual(decision['action'],'WAIT_FOR_REVIEW');self.assertFalse(decision['notify'])
        self.assertEqual(f.rows('outbox'),[]);self.assertEqual(f.rows('analysis_jobs')[0]['state'],'FAILED')

    def test_prepare_ai_publication_and_top_share_roles_without_losing_watch_reports(self):
        for with_plan,role,bucket in ((True,control.TOP,'cards'),(False,control.WATCH,'rising_watch')):
            f,rows,s,m=self.sample(with_plan)
            with patch.object(KI,'fetch_opportunity_spread',return_value={}):
                batch=KI.company_review.prepare(KI,f.store,'cycle',rows,NOW)
            f.finish_members();KI.company_review.finalize(KI,f.store,NOW)
            payload=KI.load_payload(f.rows('company_review_batches')[0]['payload'])
            self.assertEqual(payload['decisions'][0]['orchestration']['role'],role)
            view=top.collect(KI,f.store,NOW)
            self.assertEqual(len(view[bucket]),1)
            self.assertEqual(view[bucket][0]['orchestration']['role'],role)
            if not with_plan:self.assertEqual(view['cards'],[])
            self.assertEqual(len(f.rows('outbox')),1)
            self.assertIn('WZROST Z PLANEM' if with_plan else 'WZROST DO OBSERWACJI',f.rows('outbox')[0]['message'])

    def test_ai_prompt_receives_joined_evidence_but_frozen_contract_is_not_rewritten(self):
        f,rows,s,m=self.sample(True)
        with patch.object(KI,'fetch_opportunity_spread',return_value={}):KI.company_review.prepare(KI,f.store,'cycle',rows,NOW)
        ev=KI.load_payload(f.rows('events')[0]['payload']);ctx={'sources':[],'cutoff':s['acquired_at']}
        ctx['analysis_manifest']=KI.build_analysis_manifest(ev,ctx)
        ctx['analysis_manifest'].update(review_contract=KI.evidence_review.CURRENT_CONTRACT,orchestration=self.assess(s,m))
        request=KI.event_analysis_request(ev,ctx)
        book=json.loads(request['messages'][-1]['content'])['evidence_review']
        self.assertEqual(book['orchestration']['role'],control.TOP)
        self.assertIn('connections',book['orchestration']);self.assertIn('ostrzeżenie spadkowe',request['messages'][0]['content'])

    def test_two_declines_get_one_warning_digest_and_never_fill_rising_top5(self):
        f=fixtures.FinalCompanyReviewTests();f.setUp();self.addCleanup(f.doCleanups)
        rows=f.candidates(2,direction=-1)
        with patch.object(KI,'fetch_opportunity_spread',return_value={}):KI.company_review.prepare(KI,f.store,'cycle',rows,NOW)
        with f.store.transaction() as db:
            for row in db.execute('SELECT e.id,e.payload FROM events e JOIN analysis_jobs j ON j.event_id=e.id').fetchall():
                ev=KI.load_payload(row['payload'])
                db.execute("UPDATE analysis_jobs SET state='PENDING_AI',context=? WHERE event_id=?",(KI.json_text({'sources':[],'cutoff':ev['snapshot']['acquired_at']}),row['id']))
        response={'choices':[{'finish_reason':'stop','message':{'content':json.dumps({'final_review':{'attention':'INFORM'}})}}],
                  'usage':{'total_tokens':1}}
        with patch.object(KI,'service_http',side_effect=fixtures.model_transport(response)) as provider:
            for _ in range(2):self.assertTrue(KI.process_analysis_once(f.store,{'OPENAI_API_KEY':'fake'}))
        self.assertEqual(provider.call_count,2)
        for job in f.rows('analysis_jobs'):self.assertEqual(job['state'],'DONE',job['last_error'])
        KI.company_review.finalize(KI,f.store,NOW)
        view=top.collect(KI,f.store,NOW)
        self.assertEqual(view['cards'],[]);self.assertEqual(view['rising_watch'],[])
        self.assertEqual(len(view['warnings']),2)
        self.assertEqual(len(f.rows('outbox')),1)
        message=f.rows('outbox')[0]['message']
        self.assertEqual(message.count('OSTRZEŻENIE SPADKOWE'),2)
        self.assertNotIn('WZROST Z PLANEM',message)

    def test_readonly_status_view_shows_waiting_company_without_triggering_api(self):
        from streamlit.testing.v1 import AppTest
        f,rows,s,m=self.sample();decision=self.assess(s,m)
        with f.store.transaction() as db:control.save(KI,db,decision)
        script='import KI\nimport company_orchestrator as co\nfrom pathlib import Path\nco.render_status(KI,KI.Store(Path('+repr(str(f.store.path))+')))'
        with patch.object(KI,'service_http',side_effect=AssertionError('API')):
            app=AppTest.from_string(script).run(timeout=30)
            self.assertFalse(app.exception,list(app.exception))
            selector=next(x for x in app.text_input if x.label=='Ticker — decyzja orkiestratora')
            self.assertEqual(selector.value,'')
            selector.set_value('  '+s['ticker'].lower()+'  ').run(timeout=30)
            self.assertFalse(app.exception,list(app.exception))
            self.assertTrue(any('Następny warunek' in x.value for x in app.markdown))
            next(x for x in app.text_input if x.label=='Ticker — decyzja orkiestratora').set_value('UNKNOWN').run(timeout=30)
            self.assertFalse(app.exception,list(app.exception))
            self.assertTrue(any('Brak zapisanej decyzji' in x.value for x in app.info))


if __name__=='__main__':unittest.main()
