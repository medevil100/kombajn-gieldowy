"""Large-potential selection/lifecycle with real fixture SQLite; no paid providers."""
import copy
import json
from datetime import datetime,timedelta,time,timezone
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import KI
import large_movement as large
import company_orchestrator
import ki_assistant
from test_company_narrative_20261113 import fixture_narrative

NOW=datetime(2026,11,13,15,30,tzinfo=timezone.utc)


def daily_sample(n=80):
    days=[];day=NOW.date()-timedelta(days=1)
    while len(days)<n:
        if KI.exchange_session_bounds('AAA',day.isoformat()):days.append(day)
        day-=timedelta(days=1)
    rows=[]
    for i,day in enumerate(reversed(days)):
        close=.85+.15*i/max(1,n-1)
        row={'time':datetime.combine(day,time.min,KI.exchange_zone('AAA')).isoformat(),
             'end':KI.exchange_session_bounds('AAA',day.isoformat())[1].isoformat(),
             'status':'CLOSED','open':close,'close':close,'high':close+.05,'low':close-.05,'volume':100000.}
        if i in (10,25,40):row['high']=2.0 if i!=25 else 2.3
        if i in (6,20,35):row['low']=.6
        rows.append(row)
    return rows


def sample(ticker='AAA',at=NOW,price=1.2):
    s=KI.opportunity_test_snapshot(at,ticker,price)
    start=at.replace(minute=30,second=0,microsecond=0)
    if start>at:start-=timedelta(hours=1)
    closed={'time':(start-timedelta(hours=1)).isoformat(),'end':start.isoformat(),'status':'CLOSED',
            'open':1.05,'high':max(price,1.25),'low':1.,'close':price,'volume':300000.,'rvol':2.5,'average_volume':120000.}
    s.update(company_name='Example Company Inc.',company_website='https://example.com',currency='USD',
        price_basis={'blocked':False,'status':'NO_ACTION_REPORTED','events':[]},corporate_actions=[],
        candle_time=start.isoformat(),candle_end=(start+timedelta(hours=1)).isoformat(),candle_status='OPEN',
        previous_closed=closed,price_matrix={'state':'CONFIRMED','reference_status':'READY','reference_session':'2026-11-12',
          'anchor_price':1.,'anchor_at':'2026-11-12T16:00:00-05:00','change_pct':(price-1)*100,
          'last_price':price,'last_acquired_at':at.isoformat(),'last_candle_time':start.isoformat(),
          'consecutive_reads':3,'activity_verified':True},
        ohlc={'open':1.1,'high':max(1.25,price),'low':1.,'close':price},
        trend_context={'horizons':{'short':{'direction':'UP'},'medium':{'direction':'UP'},'long':{'direction':'UNKNOWN'}}},
        chart_history=[closed,{'time':start.isoformat(),'end':(start+timedelta(hours=1)).isoformat(),'status':'OPEN',
                              'open':1.1,'high':max(price,1.25),'low':1.,'close':price,'volume':100000.}])
    s['indicators'].update(ma_fast=1.1,last_macd_hist=.02)
    return s


def wire(material,verdict='ACTIVE'):
    evidence=material['evidence'];support=list(evidence['support'])
    selected=[x for x in ('B_BREAKOUT','B_VOLUME') if x in support] or support[:2]
    target=next((k for k,v in material['targets'].items() if v['price']/material['snapshot']['price']>=1.5),'NONE')
    return {'verdict':verdict,'supporting_evidence':selected,'risk_evidence':list(evidence['risk'])[:2],
            'target_id':target,'invalidation_id':next(iter(material['invalidation_levels']),'NONE'),
            'time_window':'W4_8' if 'W4_8' in material['time_windows'] else 'W1_3',
            'time_basis':'TB_TECHNICAL','time_evidence':selected,
            'target_reason':'NO_TARGET' if target=='NONE' else 'RANGE_PROJECTION' if material['targets'][target]['kind']=='MEASURED_RANGE' else 'HISTORICAL_STRUCTURE',
            'time_reason':'BREAKOUT_AND_ACTIVITY',
            'confirmation':'BREAKOUT_AND_ACTIVITY','estimate_confidence':'LOW','narrative':fixture_narrative()}


def body(choice):
    return {'choices':[{'finish_reason':'stop','message':{'content':json.dumps(choice)}}],
            'usage':{'prompt_tokens':1234,'completion_tokens':120}}


class LargeMovementTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        self.store=KI.Store(Path(temp.name)/'fixture.sqlite3')
        self.store.save_section('settings',{'pipeline_enabled':True,'telegram_enabled':True,'price_threshold_pct':2.,'final_company_review_enabled':True})
        self.store.save_section('tickers',['AAA'])
        self.daily=daily_sample();KI._save_daily_history(self.store,'AAA',self.daily,NOW)
        with self.store.transaction() as c:
            c.execute('INSERT INTO runtime VALUES(?,?,?)',('market_intelligence:daily:AAA',KI.json_text({'rows':self.daily,'acquired_at':(NOW-timedelta(minutes=1)).isoformat()}),NOW.isoformat()))
        self.s=sample();self.local=large.setup(self.s,self.daily)

    def packet(self):return large.packet(KI,self.store,self.s,self.daily,self.local)

    def queue(self,cycle='cycle'):
        self.assertEqual(large.consider(KI,self.store,self.s,cycle,NOW.isoformat()),'QUEUED')
        with self.store.connection() as c:return dict(c.execute('SELECT * FROM large_movement_jobs ORDER BY created_at DESC LIMIT 1').fetchone())

    def process(self,verdict='ACTIVE',choice=None,now=NOW):
        def response(*args,**kwargs):
            material=json.loads(args[3]['messages'][-1]['content'])
            return body(choice or wire(material,verdict))
        return large.process_once(KI,self.store,{'OPENAI_API_KEY':'fixture'},now.isoformat(),response)

    def case(self):
        with self.store.connection() as c:
            row=c.execute('SELECT * FROM large_movement_cases WHERE ticker=?',('AAA',)).fetchone()
            return dict(row) if row else None

    def test_qualifies_before_top5_with_no_short_two_target_plan(self):
        self.assertTrue(self.local['eligible'])
        self.assertEqual(KI.build_trade_plan(self.s,20.,now=NOW)['status'],'UNAVAILABLE')
        self.queue()

    def test_ai_receives_all_available_daily_bars_not_only_sixty(self):
        material=self.packet()
        self.assertEqual(len(material['daily_candles']),80)
        self.assertEqual(material['daily_coverage']['requested_weeks'],52)
        self.assertEqual(material['daily_coverage']['first_session'],self.daily[0]['time'])

    def test_near_resistance_has_priority_over_distant_hundred_percent_target(self):
        material=self.packet();material['snapshot']['price']=4.64
        material['targets']={'T1':{'price':4.78,'time':self.daily[10]['time'],'kind':'DAILY_PIVOT','basis':'Opór'},
                             'T2':{'price':9.6,'time':self.daily[25]['time'],'kind':'DAILY_PIVOT','basis':'Szczyt'}}
        material['invalidation_levels']={'S1':{'price':3.762,'time':self.daily[20]['time'],'kind':'DAILY_PIVOT','basis':'Wsparcie'}}
        value=wire(material);context=large.concrete_context(material,material['targets']['T2'],material['invalidation_levels']['S1'])
        self.assertAlmostEqual(context['first_upside_pct'],3.0172413793)
        self.assertAlmostEqual(context['invalidation_distance_pct'],18.9224137931)
        self.assertLess(context['first_rr'],.16)
        with self.assertRaisesRegex(ValueError,'Bliski opór'):large.decode(KI,body(value),material,large.request(KI,material))
        value['verdict']='WATCHING'
        result=large.decode(KI,body(value),material,large.request(KI,material))
        self.assertEqual(result['concrete']['first_level']['price'],4.78)

    def test_volumes_are_numbers_and_data_availability_is_not_support(self):
        material=self.packet();support=material['evidence']['support']
        self.assertNotIn('B_DATA',support)
        self.assertIn('300000',support['B_VOLUME']);self.assertIn('2.5',support['B_VOLUME'])

    def test_time_explanation_needs_selected_daily_or_breakout_evidence(self):
        material=self.packet();value=wire(material);value['time_evidence']=['B_VOLUME']
        with self.assertRaisesRegex(ValueError,'Czas bez'):large.decode(KI,body(value),material,large.request(KI,material))

    def test_corporate_basis_and_too_short_history_block_before_model(self):
        self.s['price_basis']['blocked']=True
        self.assertFalse(large.setup(self.s,self.daily)['eligible'])
        self.s['price_basis']['blocked']=False
        self.assertFalse(large.setup(self.s,self.daily[:19])['eligible'])

    def test_open_partial_volume_is_not_extrapolated_to_full_activity(self):
        self.s['previous_closed']['rvol']=.2
        self.s['rvol']=10.;self.s['volume']=100000000
        self.assertFalse(large.setup(self.s,self.daily)['eligible'])

    def test_future_pivots_are_not_eligible_targets(self):
        rows=self.daily+[{**self.daily[-1],'time':(NOW+timedelta(days=1)).isoformat(),'end':(NOW+timedelta(days=2)).isoformat(),'high':999}]
        filtered=KI.market_intelligence.closed_rows(rows,NOW)
        targets,_=large.levels(filtered,self.s['price'],self.local)
        self.assertNotIn(999,[v['price'] for v in targets.values()])

    def test_target_price_and_potential_are_locally_derived_from_selected_level(self):
        material=self.packet();prepared=large.request(KI,material)
        result=large.decode(KI,body(wire(material)),material,prepared)
        self.assertEqual(result['target']['price'],2.)
        self.assertAlmostEqual(result['potential_pct'],(2/1.2-1)*100)
        self.assertIn('niekalibrowanym',result['scope'])

    def test_holding_time_has_separate_evidence_and_confidence(self):
        material=self.packet();result=large.decode(KI,body(wire(material)),material,large.request(KI,material))
        self.assertEqual(result['time_label'],'4–8 tygodni');self.assertEqual(result['time_confidence'],'niska')
        self.assertTrue(result['time_why'])

    def test_six_month_time_is_unavailable_without_long_daily_history(self):
        material=self.packet();self.assertNotIn('M2_6',material['time_windows'])
        choice=wire(material);choice['time_window']='M2_6'
        with self.assertRaises(ValueError):large.decode(KI,body(choice),material,large.request(KI,material))

    def test_active_cannot_use_missing_target_or_invalidation_or_time(self):
        material=self.packet();prepared=large.request(KI,material)
        for field in ('target_id','invalidation_id'):
            choice=wire(material);choice[field]='NONE'
            with self.assertRaises(ValueError):large.decode(KI,body(choice),material,prepared)
        choice=wire(material);choice.update(time_window='UNESTIMATED',time_basis='TB_UNKNOWN')
        with self.assertRaises(ValueError):large.decode(KI,body(choice),material,prepared)

    def test_early_watch_can_keep_unestimated_time_without_invented_return(self):
        material=self.packet();choice=wire(material,'WATCHING');choice.update(target_id='NONE',target_reason='NO_TARGET',time_window='UNESTIMATED',time_basis='TB_UNKNOWN',time_reason='INSUFFICIENT_TIME_EVIDENCE')
        result=large.decode(KI,body(choice),material,large.request(KI,material))
        self.assertIsNone(result['potential_pct']);self.assertIsNone(result['review_after'])

    def test_unknown_evidence_and_own_price_fields_are_rejected(self):
        material=self.packet();prepared=large.request(KI,material)
        choice=wire(material);choice['target_price']=100.
        with self.assertRaises(ValueError):large.decode(KI,body(choice),material,prepared)
        choice=wire(material);choice['supporting_evidence']=['B_INVENTED']
        with self.assertRaises(ValueError):large.decode(KI,body(choice),material,prepared)

    def test_actual_day_and_week_surges_remain_mandatory_risks(self):
        s=copy.deepcopy(self.s);s['price_matrix']['change_pct']=100.
        local={**self.local,'change_5_sessions_pct':200.}
        m=large.packet(KI,self.store,s,self.daily,local);r=large.decode(KI,body(wire(m)),m,large.request(KI,m))
        self.assertTrue(any('część wzrostu już' in text for text in r['risks']))

    def test_one_model_call_creates_persistent_case_and_records_usage(self):
        self.queue();self.assertTrue(self.process());row=self.case()
        self.assertEqual(row['status'],'ACTIVE')
        with self.store.connection() as c:
            job=c.execute('SELECT state,input_tokens,output_tokens FROM large_movement_jobs').fetchone()
        self.assertEqual(tuple(job),('DONE',1234,120))

    def test_same_snapshot_and_small_price_changes_do_not_repeat_ai(self):
        self.queue();self.process()
        self.assertEqual(large.consider(KI,self.store,self.s,'again',NOW.isoformat()),'NO_MATERIAL_CHANGE')
        s=sample(at=NOW+timedelta(minutes=45),price=1.21)
        self.assertEqual(large.consider(KI,self.store,s,'again',s['acquired_at']),'NO_MATERIAL_CHANGE')

    def test_significant_new_price_can_trigger_intraday_update_after_thirty_minutes(self):
        self.queue();self.process()
        s=sample(at=NOW+timedelta(minutes=45),price=1.4)
        self.assertEqual(large.consider(KI,self.store,s,'again',s['acquired_at']),'QUEUED')

    def test_failed_model_is_not_automatically_retried(self):
        self.queue();calls=[]
        def fail(*a,**k):calls.append(1);raise OSError('fixture')
        large.process_once(KI,self.store,{'OPENAI_API_KEY':'fixture'},NOW.isoformat(),fail)
        self.assertFalse(large.process_once(KI,self.store,{'OPENAI_API_KEY':'fixture'},NOW.isoformat(),fail))
        self.assertEqual(len(calls),1)

    def test_missing_key_makes_no_provider_call(self):
        self.queue()
        with patch.object(KI,'service_http',side_effect=AssertionError('provider')):
            large.process_once(KI,self.store,{},NOW.isoformat())
        with self.store.connection() as c:self.assertEqual(c.execute('SELECT state FROM large_movement_jobs').fetchone()[0],'KEY_MISSING')

    def test_budget_rejects_before_network(self):
        self.queue()
        with self.store.transaction() as c:
            for n in range(large.MAX_CALLS_DAY):
                c.execute('INSERT INTO large_movement_jobs(id,ticker,cycle_id,state,created_at,started_at,packet) VALUES(?,?,?,?,?,?,?)',
                    ('used'+str(n),'ZZZ','prior','FAILED',NOW.isoformat(),NOW.isoformat(),'{}'))
        with patch.object(KI,'service_http',side_effect=AssertionError('provider')):large.process_once(KI,self.store,{'OPENAI_API_KEY':'fixture'},NOW.isoformat())
        with self.store.connection() as c:self.assertEqual(c.execute("SELECT state FROM large_movement_jobs WHERE ticker='AAA'").fetchone()[0],'DAILY_LIMIT')

    def test_case_remains_after_seven_days_and_when_removed_from_intraday_rank(self):
        self.queue();self.process();self.store.save_section('tickers',[])
        with self.store.transaction() as c:c.execute('DELETE FROM opportunities')
        page=large.case_page(self.store,('ACTIVE',),ticker='AAA')
        self.assertEqual(page['total'],1);self.assertEqual(page['rows'][0]['ticker'],'AAA')

    def test_time_expiry_marks_review_due_instead_of_deleting_case(self):
        self.queue();self.process();s=sample(at=NOW+timedelta(days=70),price=1.3)
        large.update_case(KI,self.store,s,[], 'later')
        self.assertEqual(self.case()['status'],'REVIEW_DUE')

    def test_full_daily_close_below_invalidation_ends_thesis(self):
        self.queue();self.process();case=self.case();r=KI.load_payload(case['result']);level=r['invalidation']['price']
        later={**self.daily[-1],'close':level*.9,'end':(NOW+timedelta(days=1)).isoformat()}
        s=sample(at=NOW+timedelta(days=1,minutes=5),price=1.)
        large.update_case(KI,self.store,s,[later],'later')
        self.assertEqual(self.case()['status'],'INVALIDATED')

    def test_intraday_dip_is_not_a_full_session_close(self):
        self.queue();self.process();s=sample(at=NOW+timedelta(minutes=15),price=.5)
        large.update_case(KI,self.store,s,self.daily,'later')
        self.assertEqual(self.case()['status'],'ACTIVE')

    def test_target_reached_is_not_reported_as_realized_profit(self):
        self.queue();self.process();s=sample(at=NOW+timedelta(minutes=15),price=2.1)
        large.update_case(KI,self.store,s,self.daily,'later')
        self.assertEqual(self.case()['status'],'TARGET_REACHED')
        self.assertIn('nie jest to potwierdzenie',KI.load_payload(self.case()['result'])['monitoring']['reason'])

    def test_split_blocks_old_case_comparison_and_target(self):
        self.queue();self.process();s=sample(at=NOW+timedelta(days=1),price=24.)
        s['corporate_actions']=[{'effective_at':(NOW+timedelta(hours=5)).isoformat(),'new_per_old':.05}]
        large.update_case(KI,self.store,s,self.daily,'later')
        self.assertEqual(self.case()['status'],'BASIS_REVIEW')

    def test_digest_is_grouped_deduplicated_and_uses_existing_outbox(self):
        self.queue();self.process();large.finalize(KI,self.store,NOW.isoformat());large.finalize(KI,self.store,NOW.isoformat())
        with self.store.connection() as c:
            rows=c.execute('SELECT kind,message FROM outbox').fetchall()
        self.assertEqual(len(rows),1);self.assertEqual(rows[0]['kind'],'LARGE_MOVEMENT_DIGEST')
        self.assertIn('4–8 tygodni',rows[0]['message'])
        claimed=KI.claim_delivery(self.store,now=NOW)
        self.assertEqual(claimed['kind'],'LARGE_MOVEMENT_DIGEST')

    def test_invalidated_case_blocks_old_pending_positive_digest(self):
        self.queue();self.process();large.finalize(KI,self.store,NOW.isoformat())
        with self.store.transaction() as c:c.execute("UPDATE large_movement_cases SET status='INVALIDATED'")
        self.assertIsNone(KI.claim_delivery(self.store,now=NOW))

    def test_telegram_off_preserves_case_without_sending(self):
        self.queue();self.process();self.store.update_settings({'telegram_enabled':False})
        large.finalize(KI,self.store,NOW.isoformat())
        with self.store.connection() as c:self.assertEqual(c.execute('SELECT count(*) FROM outbox').fetchone()[0],0)
        self.assertEqual(self.case()['status'],'ACTIVE')

    def test_central_orchestrator_schedules_research_without_top5_membership(self):
        with patch.object(KI,'service_http',side_effect=AssertionError('network')):
            result=company_orchestrator.coordinate_large_movement(KI,self.store,self.s,'cycle',NOW.isoformat())
        self.assertEqual(result['status'],'QUEUED')
        with self.store.connection() as c:
            self.assertEqual(c.execute('SELECT reason FROM issuer_watch_jobs').fetchone()[0],'LARGE_POTENTIAL')
            self.assertEqual(c.execute('SELECT count(*) FROM analysis_jobs').fetchone()[0],0)

    def test_pending_news_defers_model_for_bounded_time(self):
        company_orchestrator.coordinate_large_movement(KI,self.store,self.s,'cycle',NOW.isoformat())
        with patch.object(KI,'service_http',side_effect=AssertionError('network')):
            self.assertFalse(large.process_once(KI,self.store,{'OPENAI_API_KEY':'fixture'},NOW.isoformat()))

    def test_reader_exposes_same_case_without_provider_calls(self):
        self.queue();self.process()
        reader=ki_assistant.Reader(self.store.path,KI)
        result=reader.run('company',{'ticker':'AAA'})
        self.assertEqual(result['data']['large_movement_case']['status'],'ACTIVE')

    def test_sixteen_cases_are_all_accessible_by_page(self):
        self.queue();self.process();row=self.case()
        with self.store.transaction() as c:
            for n in range(15):
                r={**row,'ticker':'B'+str(n)}
                c.execute('INSERT INTO large_movement_cases VALUES(?,?,?,?,?,?,?,?,?,?,?)',tuple(r[k] for k in
                    ('ticker','status','opened_at','updated_at','market_at','price','currency','result','job_id','notice_cycle','notified_version')))
        first=large.case_page(self.store,('ACTIVE',),page=1);second=large.case_page(self.store,('ACTIVE',),page=2)
        self.assertEqual(first['total'],16);self.assertEqual(len(first['rows'])+len(second['rows']),16)

    def test_deadline_maintenance_works_without_new_market_quote(self):
        self.queue();self.process()
        large.maintenance(KI,self.store,(NOW+timedelta(days=70)).isoformat())
        self.assertEqual(self.case()['status'],'REVIEW_DUE')

    def test_schema_does_not_offer_active_without_large_target(self):
        material=self.packet();material['targets']={}
        schema=large.request(KI,material)['response_format']['json_schema']['schema']['properties']
        self.assertNotIn('ACTIVE',schema['verdict']['enum'])
        self.assertEqual(schema['target_id']['enum'],['NONE'])

    def test_first_invalid_response_is_visible_without_positive_forecast(self):
        self.queue()
        large.process_once(KI,self.store,{'OPENAI_API_KEY':'fixture'},NOW.isoformat(),lambda *a,**k:body({}))
        row=self.case();self.assertEqual(row['status'],'REVIEW_FAILED')
        self.assertIsNone(json.loads(row['result'])['potential_pct'])

    def test_non_string_evidence_is_a_validation_error(self):
        material=self.packet();value=wire(material);value['supporting_evidence']=[{}]
        with self.assertRaises(ValueError):large.decode(KI,body(value),material,large.request(KI,material))

    def test_streamlit_view_renders_and_accepts_ticker_without_network(self):
        from streamlit.testing.v1 import AppTest
        self.queue();self.process()
        source='import KI,large_movement\nstore=KI.Store('+repr(str(self.store.path))+')\nlarge_movement.render(KI,store)'
        with patch.object(KI,'service_http',side_effect=AssertionError('network')):
            app=AppTest.from_string(source,default_timeout=20).run()
            self.assertEqual(len(app.exception),0)
            app.text_input(key='large_ticker').set_value('AAA').run()
            self.assertEqual(len(app.exception),0)
            app.radio(key='large_market').set_value('GPW').run()
            self.assertEqual(len(app.exception),0)

    def test_mobile_html_escapes_strings_and_has_separate_time_potential(self):
        self.queue();self.process();row=self.case();row['ticker']='<script>x</script>'
        markup=large.cards_html(KI,[row])
        self.assertNotIn('<script>',markup);self.assertIn('Szacowany horyzont AI',markup)
        self.assertIn('Potencjał od tej ceny',markup);self.assertIn('flex-wrap:wrap',markup)


if __name__=='__main__':unittest.main()
