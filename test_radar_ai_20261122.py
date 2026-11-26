import copy
import json
import tempfile
import unittest
from pathlib import Path
from datetime import timedelta
from unittest.mock import patch
import KI
import radar_ai
import technical_radar
import test_large_movement_20261113 as fixtures
from test_company_narrative_20261113 import fixture_narrative


class RadarAIReviewTests(unittest.TestCase):
    def setUp(self):
        mode=patch.object(technical_radar,'enabled',return_value=True);mode.start();self.addCleanup(mode.stop)
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.store=KI.Store(Path(self.temp.name)/'test.sqlite3')
        self.now=fixtures.NOW
        self.rows=fixtures.daily_sample()
        self.store.update_settings({'pipeline_enabled':True,'technical_radar_enabled':True,'telegram_enabled':False})

    def seed(self,ticker='AAA',score=80,price=1.2,at=None):
        at=at or self.now;snap=fixtures.sample(ticker,at,price)
        state=technical_radar.evaluate(snap,self.rows);state.update(growth_score=score,decline_score=0)
        with self.store.transaction() as c:
            technical_radar.schema(c)
            c.execute('INSERT OR REPLACE INTO technical_radar VALUES(?,?,?)',(ticker,snap['acquired_at'],KI.json_text(state)))
            c.execute('INSERT INTO observations(ticker,interval,candle_time,acquired_at,candle_status,payload) VALUES(?,?,?,?,?,?)',
                (ticker,'1h',snap['candle_time'],snap['acquired_at'],snap['candle_status'],KI.encode_observation(snap)))
        return snap,state

    def schedule(self,at=None):
        with patch('large_movement.daily_rows',return_value=self.rows),patch.object(KI.issuer_watch,'enqueue'):
            return radar_ai.schedule(KI,self.store,at or self.now)

    def rows_jobs(self):
        with self.store.connection() as c:return [dict(r) for r in c.execute('SELECT * FROM radar_ai_jobs ORDER BY created_at,id')]

    def body(self):
        return {'choices':[{'finish_reason':'stop','message':{'content':json.dumps({'verdict':'WATCH','narrative':fixture_narrative(full=True)})}}],
                'usage':{'prompt_tokens':100,'completion_tokens':200}}

    def test_only_top5_large_and_portfolio_are_selected_with_one_job_per_ticker(self):
        for i in range(7):self.seed('A'+str(i),score=90-i)
        self.seed('PORT',score=10);self.seed('LONG',score=20)
        KI.portfolio_save(self.store,[{'ticker':'PORT','shares':5,'entry_price':1.}])
        with self.store.transaction() as c:
            c.execute('INSERT INTO technical_watch VALUES(?,?,?,?,?)',('LONG',self.now.isoformat(),self.now.isoformat(),'LARGE',KI.json_text({'large_since':self.now.isoformat()})))
        self.assertEqual(self.schedule(),7)
        jobs=self.rows_jobs();self.assertEqual(len({j['ticker'] for j in jobs}),7)
        groups={j['ticker']:json.loads(j['packet'])['selection']['roles'] for j in jobs}
        self.assertEqual(groups['PORT'],['PORTFOLIO']);self.assertEqual(groups['LONG'],['LARGE'])
        self.assertNotIn('A6',groups)

    def test_guarded_worker_calls_ai_and_retains_authored_report_and_usage(self):
        self.seed();self.assertEqual(self.schedule(),1)
        with patch.object(KI,'service_http',return_value=self.body()) as transport:
            self.assertTrue(radar_ai.process_once(KI,self.store,{'OPENAI_API_KEY':'fixture'},self.now))
            self.assertFalse(radar_ai.process_once(KI,self.store,{'OPENAI_API_KEY':'fixture'},self.now))
        self.assertEqual(transport.call_count,1)
        job=self.rows_jobs()[0];self.assertEqual(job['state'],'DONE')
        self.assertEqual((job['input_tokens'],job['output_tokens']),(100,200))
        self.assertIn('1,2 USD',json.loads(job['result'])['narrative']['sections']['summary']['text'])
        prepared=json.loads(job['request']);self.assertEqual(prepared['model'],'gpt-6-luna')
        self.assertEqual(prepared['reasoning_effort'],'none')
        self.assertEqual(prepared['max_completion_tokens'],6600)
        user=json.loads(prepared['messages'][1]['content'])
        facts=user['narrative_facts']
        self.assertIn('derived.target_distance_pct',facts)
        reference_rule=prepared['response_format']['json_schema']['schema']['properties']['narrative']['properties']['technical']['properties']['references']['items']
        self.assertNotIn('enum',reference_rule)
        self.assertEqual(reference_rule['type'],'string')
        self.assertLess(len(json.dumps(prepared)),160000)

    def test_same_material_and_cooldown_do_not_create_another_paid_task(self):
        self.seed();self.schedule()
        radar_ai.process_once(KI,self.store,{'OPENAI_API_KEY':'fixture'},self.now,transport=lambda *a,**k:self.body())
        later=self.now+timedelta(minutes=15)
        self.seed(at=later);self.assertEqual(self.schedule(later),0)
        later=self.now+timedelta(minutes=31)
        self.seed(price=1.3,at=later);self.assertEqual(self.schedule(later),1)

    def test_material_score_change_requeues_same_company_after_cooldown(self):
        self.seed(score=70);self.schedule()
        radar_ai.process_once(KI,self.store,{'OPENAI_API_KEY':'fixture'},self.now,transport=lambda *a,**k:self.body())
        later=self.now+timedelta(minutes=31)
        self.seed(score=80,at=later)
        self.assertEqual(self.schedule(later),1)

    def test_daily_shared_limit_defers_latest_packet_and_requeues_next_day(self):
        self.seed();self.schedule()
        with self.store.transaction() as c:
            for i in range(radar_ai.large_movement.MAX_CALLS_DAY):
                c.execute('INSERT INTO radar_ai_jobs(id,ticker,state,created_at,market_at,started_at,packet) VALUES(?,?,?,?,?,?,?)',
                    ('used'+str(i),'OLD','DONE',self.now.isoformat(),self.now.isoformat(),self.now.isoformat(),'{}'))
        with patch.object(KI,'service_http',side_effect=AssertionError('network')):
            self.assertTrue(radar_ai.process_once(KI,self.store,{'OPENAI_API_KEY':'fixture'},self.now))
        deferred=next(j for j in self.rows_jobs() if j['ticker']=='AAA')
        self.assertEqual(deferred['state'],'DEFERRED_BUDGET');self.assertIsNone(deferred['finished_at'])
        later=self.now+timedelta(hours=1)
        self.seed(price=1.4,at=later);self.assertEqual(self.schedule(later),0)
        refreshed=next(j for j in self.rows_jobs() if j['ticker']=='AAA')
        self.assertEqual(refreshed['state'],'DEFERRED_BUDGET')
        self.assertEqual(refreshed['market_at'],later.isoformat())
        tomorrow=self.now+timedelta(days=3)
        self.seed(price=1.5,at=tomorrow);self.assertEqual(self.schedule(tomorrow),1)
        queued=next(j for j in self.rows_jobs() if j['ticker']=='AAA')
        self.assertEqual(queued['state'],'QUEUED');self.assertEqual(queued['market_at'],tomorrow.isoformat())

    def test_failure_is_saved_and_never_automatically_retried(self):
        self.seed();self.schedule()
        with patch.object(KI,'service_http',side_effect=OSError('fixture')) as provider:
            radar_ai.process_once(KI,self.store,{'OPENAI_API_KEY':'fixture'},self.now)
            radar_ai.process_once(KI,self.store,{'OPENAI_API_KEY':'fixture'},self.now)
        self.assertEqual(provider.call_count,1);self.assertEqual(self.rows_jobs()[0]['state'],'FAILED')
        self.assertEqual(self.schedule(self.now+timedelta(minutes=15)),0)

    def test_no_pipeline_or_stale_material_never_calls_provider(self):
        self.seed();self.schedule()
        self.store.update_settings({'pipeline_enabled':False})
        self.assertFalse(radar_ai.process_once(KI,self.store,{} ,self.now))
        self.store.update_settings({'pipeline_enabled':True})
        with patch.object(KI,'service_http',side_effect=AssertionError('network')):
            self.assertTrue(radar_ai.process_once(KI,self.store,{'OPENAI_API_KEY':'fixture'},self.now+timedelta(hours=1)))
        self.assertEqual(self.rows_jobs()[0]['state'],'EXPIRED')

    def test_three_roles_share_one_job_and_analysis_worker_dispatches_it(self):
        self.seed()
        KI.portfolio_save(self.store,[{'ticker':'AAA','shares':10,'entry_price':1.}])
        with self.store.transaction() as c:
            c.execute('INSERT INTO technical_watch VALUES(?,?,?,?,?)',('AAA',self.now.isoformat(),self.now.isoformat(),'LARGE',KI.json_text({'large_since':self.now.isoformat()})))
        self.assertEqual(self.schedule(),1)
        self.assertEqual(set(json.loads(self.rows_jobs()[0]['packet'])['selection']['roles']),{'TOP5','LARGE','PORTFOLIO'})
        self.assertTrue(KI.service_work_due(self.store,'analysis',self.now))
        with patch('radar_ai.process_once',return_value=True) as worker:
            self.assertTrue(KI.process_analysis_once(self.store,{'OPENAI_API_KEY':'fixture'}))
            worker.assert_called_once()

    def test_selected_groups_schedule_tavily_with_existing_queue_and_no_network(self):
        self.seed()
        with patch('large_movement.daily_rows',return_value=self.rows),patch.object(KI,'service_http',side_effect=AssertionError('network')):
            self.assertEqual(radar_ai.schedule(KI,self.store,self.now),1)
        with self.store.connection() as c:
            self.assertEqual(c.execute('SELECT count(*) FROM issuer_watch_jobs').fetchone()[0],1)
        with patch.object(KI,'service_http',side_effect=AssertionError('network')):
            self.assertFalse(radar_ai.process_once(KI,self.store,{'OPENAI_API_KEY':'fixture'},self.now))

    def test_manual_active_large_review_bypasses_automatic_limit_and_is_deduplicated(self):
        self.seed()
        with self.store.transaction() as c:
            radar_ai.schema(c)
            c.execute('INSERT INTO technical_watch VALUES(?,?,?,?,?)',
                      ('AAA',self.now.isoformat(),self.now.isoformat(),'LARGE',KI.json_text({'large_since':self.now.isoformat()})))
            c.execute("INSERT INTO large_movement_cases VALUES('AAA','ACTIVE',?,?,?,1.2,'USD','{}',NULL,NULL,NULL)",
                      (self.now.isoformat(),self.now.isoformat(),self.now.isoformat()))
            for i in range(12):
                c.execute('INSERT INTO radar_ai_jobs(id,ticker,state,created_at,market_at,started_at,packet) VALUES(?,?,?,?,?,?,?)',
                          ('used'+str(i),'OLD','DONE',self.now.isoformat(),self.now.isoformat(),self.now.isoformat(),'{}'))
        with patch('large_movement.daily_rows',return_value=self.rows):
            self.assertEqual(radar_ai.schedule_manual(KI,self.store,'AAA',self.now),'QUEUED')
            self.assertEqual(radar_ai.schedule_manual(KI,self.store,'AAA',self.now),'IN_PROGRESS')
        with patch.object(KI,'service_http',return_value=self.body()) as provider:
            self.assertTrue(radar_ai.process_once(KI,self.store,{'OPENAI_API_KEY':'fixture'},self.now))
        self.assertEqual(provider.call_count,1)
        manual=[j for j in self.rows_jobs() if j['ticker']=='AAA'][0]
        self.assertEqual(manual['state'],'DONE')
        self.assertTrue(json.loads(manual['packet'])['manual_requested'])

    def test_manual_portfolio_review_contains_position_metrics_and_bypasses_limit(self):
        self.seed()
        KI.portfolio_save(self.store,[{'ticker':'AAA','shares':10,'entry_price':1.,
            'entry_currency':'USD','entry_fx_pln':4.,'sl':.9,'tp':1.5}])
        with self.store.transaction() as c:
            radar_ai.schema(c)
            c.execute("INSERT INTO runtime VALUES('portfolio_usd_pln',?,?)",
                      (KI.json_text({'rate':4.2,'effective_date':'2026-11-13'}),self.now.isoformat()))
            for i in range(12):
                c.execute('INSERT INTO radar_ai_jobs(id,ticker,state,created_at,market_at,started_at,packet) VALUES(?,?,?,?,?,?,?)',
                          ('used'+str(i),'OLD','DONE',self.now.isoformat(),self.now.isoformat(),self.now.isoformat(),'{}'))
        with patch('large_movement.daily_rows',return_value=self.rows):
            self.assertEqual(radar_ai.schedule_manual_portfolio(KI,self.store,'AAA',self.now),'QUEUED')
        packet=json.loads(next(j for j in self.rows_jobs() if j['ticker']=='AAA')['packet'])
        self.assertEqual(packet['selection']['roles'],['PORTFOLIO'])
        position=packet['selection']['portfolio']
        self.assertEqual(position['metrics']['pnl_native'],2.)
        self.assertAlmostEqual(position['metrics']['pnl_pln'],10.4)
        prepared,facts=radar_ai.request(KI,packet)
        self.assertEqual(facts['portfolio.shares']['value'],10)
        self.assertEqual(facts['portfolio.pnl_native']['value'],2.)
        self.assertAlmostEqual(facts['portfolio.pnl_pln']['value'],10.4)

    def test_manual_portfolio_button_runs_selected_job_now_with_full_ki_packet(self):
        self.seed()
        KI.portfolio_save(self.store,[{'ticker':'AAA','shares':10,'entry_price':1.,'entry_currency':'USD'}])
        captured={}
        def transport(*args,**kwargs):
            captured.update(json.loads(args[3]['messages'][1]['content']))
            return self.body()
        with patch('large_movement.daily_rows',return_value=self.rows):
            state=radar_ai.run_manual_portfolio(
                KI,self.store,{'OPENAI_API_KEY':'fixture'},'AAA',self.now,transport=transport)
        self.assertEqual(state,'DONE')
        self.assertIn('selection',captured)
        self.assertIn('material',captured)
        self.assertEqual(len(captured['material']['daily_candles']),len(self.rows))
        self.assertIn('snapshot',captured['material'])
        self.assertEqual(self.rows_jobs()[0]['ticker'],'AAA')

    def test_investment_prompt_defines_roles_verdicts_breakouts_and_no_generic_output(self):
        prompt=radar_ai.analyst_instructions()
        for required in (
            'STRONG_SETUP','WATCH','WEAKENED','INSUFFICIENT',
            'Dla TOP5','Dla LARGE','Dla PORTFOLIO',
            'Brak kolejnego oporu oznacza otwartą przestrzeń',
            'co się dzieje, na jakim dowodzie, dlaczego to ważne i co zmieni ocenę',
            'Nie podejmujesz decyzji za użytkownika',
        ):
            self.assertIn(required,prompt)
        self.assertNotIn('wybrany układ uzasadnia obserwację',prompt)

    def test_prompt_and_packet_include_derived_asymmetry_and_full_history(self):
        self.seed()
        KI.portfolio_save(self.store,[{'ticker':'AAA','shares':10,'entry_price':1.,'entry_currency':'USD'}])
        with patch('large_movement.daily_rows',return_value=self.rows):
            self.assertEqual(radar_ai.schedule_manual_portfolio(KI,self.store,'AAA',self.now),'QUEUED')
        packet=json.loads(self.rows_jobs()[0]['packet'])
        prepared,facts=radar_ai.request(KI,packet,full_input=True)
        payload=json.loads(prepared['messages'][1]['content'])
        self.assertEqual(len(payload['material']['daily_candles']),len(self.rows))
        self.assertIn('derived.history_position_pct',facts)
        self.assertIn('derived.daily_volume_ratio',facts)
        self.assertIn('quality.daily_coverage',facts)
        self.assertIn('quality.indicator_count',facts)
        sections=prepared['response_format']['json_schema']['schema']['properties']['narrative']['required']
        for section in ('data_quality','momentum','fundamentals','scenarios'):
            self.assertIn(section,sections)

    def test_post_confirmation_ai_is_required_before_large_case_becomes_active(self):
        self.seed()
        saved={'lifecycle_promotion':{'basis':'CLOSED_DAILY_CONFIRMATION','to':'REVIEW_DUE'},
               'monitoring':{}}
        with self.store.transaction() as c:
            c.execute("INSERT INTO large_movement_cases VALUES('AAA','REVIEW_DUE',?,?,?,1.2,'USD',?,NULL,NULL,NULL)",
                      (self.now.isoformat(),self.now.isoformat(),self.now.isoformat(),KI.json_text(saved)))
        with patch('large_movement.daily_rows',return_value=self.rows):
            self.assertEqual(radar_ai.schedule_manual(KI,self.store,'AAA',self.now),'QUEUED')
        strong=self.body();wire=json.loads(strong['choices'][0]['message']['content']);wire['verdict']='STRONG_SETUP'
        strong['choices'][0]['message']['content']=json.dumps(wire)
        with patch.object(KI,'service_http',return_value=strong):
            self.assertTrue(radar_ai.process_once(KI,self.store,{'OPENAI_API_KEY':'fixture'},self.now))
        with self.store.connection() as c:case=dict(c.execute("SELECT * FROM large_movement_cases WHERE ticker='AAA'").fetchone())
        self.assertEqual(case['status'],'ACTIVE')
        result=json.loads(case['result'])
        self.assertEqual(result['post_confirmation_ai']['verdict'],'STRONG_SETUP')

    def test_manual_review_uses_latest_valid_saved_data_outside_freshness_window(self):
        self.seed()
        with self.store.transaction() as c:
            c.execute("INSERT INTO large_movement_cases VALUES('AAA','ACTIVE',?,?,?,1.2,'USD','{}',NULL,NULL,NULL)",
                      (self.now.isoformat(),self.now.isoformat(),self.now.isoformat()))
        later=self.now+timedelta(hours=8)
        with patch('large_movement.daily_rows',return_value=self.rows):
            self.assertEqual(radar_ai.schedule_manual(KI,self.store,'AAA',later),'QUEUED')
        with patch.object(KI,'market_session_open',return_value=False),patch.object(KI,'service_http',return_value=self.body()) as provider:
            self.assertTrue(radar_ai.process_once(KI,self.store,{'OPENAI_API_KEY':'fixture'},later))
        self.assertEqual(provider.call_count,1)
        job=next(j for j in self.rows_jobs() if j['ticker']=='AAA')
        self.assertEqual(job['state'],'DONE')
        packet=json.loads(job['packet'])
        self.assertTrue(packet['manual_requested'])
        self.assertEqual(packet['market_at'] if 'market_at' in packet else job['market_at'],self.now.isoformat())

    def test_manual_review_promotes_existing_deferred_budget_job(self):
        self.seed()
        with self.store.transaction() as c:
            radar_ai.schema(c)
            c.execute("INSERT INTO large_movement_cases VALUES('AAA','ACTIVE',?,?,?,1.2,'USD','{}',NULL,NULL,NULL)",
                      (self.now.isoformat(),self.now.isoformat(),self.now.isoformat()))
            packet={'selection':{'ticker':'AAA'},'material':{},'manual_requested':False}
            c.execute('INSERT INTO radar_ai_jobs(id,ticker,state,created_at,market_at,packet) VALUES(?,?,?,?,?,?)',
                      ('deferred','AAA','DEFERRED_BUDGET',self.now.isoformat(),self.now.isoformat(),KI.json_text(packet)))
        later=self.now+timedelta(hours=8)
        with patch('large_movement.daily_rows',return_value=self.rows):
            self.assertEqual(radar_ai.schedule_manual(KI,self.store,'AAA',later),'QUEUED')
        job=self.rows_jobs()[0];saved=json.loads(job['packet'])
        self.assertEqual(job['id'],'deferred');self.assertEqual(job['state'],'QUEUED')
        self.assertTrue(saved['manual_requested']);self.assertEqual(saved['manual_requested_at'],later.isoformat())
        self.assertEqual(saved['material']['snapshot']['acquired_at'],self.now.isoformat())
        self.assertIn('daily_candles',saved['material'])

    def test_manual_job_precedes_legacy_analysis_queue_when_old_radar_is_disabled(self):
        self.seed()
        with self.store.transaction() as c:
            radar_ai.schema(c)
            c.execute("INSERT INTO large_movement_cases VALUES('AAA','ACTIVE',?,?,?,1.2,'USD','{}',NULL,NULL,NULL)",
                      (self.now.isoformat(),self.now.isoformat(),self.now.isoformat()))
            packet={'manual_requested':True}
            c.execute('INSERT INTO radar_ai_jobs(id,ticker,state,created_at,market_at,packet) VALUES(?,?,?,?,?,?)',
                      ('manual','AAA','QUEUED',self.now.isoformat(),self.now.isoformat(),KI.json_text(packet)))
            c.execute("INSERT INTO events VALUES('legacy','OLD','1h',?,'{}')",(self.now.isoformat(),))
            c.execute("INSERT INTO analysis_jobs(event_id,state,updated_at) VALUES('legacy','PENDING_CONTEXT',?)",(self.now.isoformat(),))
        with patch.object(technical_radar,'enabled',return_value=False),patch('radar_ai.process_once',return_value=True) as worker:
            self.assertTrue(KI.process_analysis_once(self.store,{'OPENAI_API_KEY':'fixture'}))
            worker.assert_called_once()

    def test_manual_response_is_preserved_when_reference_validation_removes_every_section(self):
        self.seed()
        with self.store.transaction() as c:
            c.execute("INSERT INTO large_movement_cases VALUES('AAA','ACTIVE',?,?,?,1.2,'USD','{}',NULL,NULL,NULL)",
                      (self.now.isoformat(),self.now.isoformat(),self.now.isoformat()))
        with patch('large_movement.daily_rows',return_value=self.rows):
            self.assertEqual(radar_ai.schedule_manual(KI,self.store,'AAA',self.now),'QUEUED')
        raw={'summary':{'text':'Pełna ręczna odpowiedź użytkownika.','references':['nieistniejacy.fakt']}}
        body={'choices':[{'finish_reason':'stop','message':{'content':json.dumps({'verdict':'WATCH','narrative':raw})}}],
              'usage':{'prompt_tokens':50000,'completion_tokens':100}}
        with patch.object(KI,'service_http',return_value=body):
            self.assertTrue(radar_ai.process_once(KI,self.store,{'OPENAI_API_KEY':'fixture'},self.now))
        job=self.rows_jobs()[0];self.assertEqual(job['state'],'MANUAL_RAW')
        saved=json.loads(job['result'])
        self.assertEqual(saved['raw_narrative'],raw);self.assertIn('kontrolę odwołań',saved['validation_error'])


class LegacyGroupTests(unittest.TestCase):
    seed=RadarAIReviewTests.seed
    schedule=RadarAIReviewTests.schedule
    rows_jobs=RadarAIReviewTests.rows_jobs
    body=RadarAIReviewTests.body

    def setUp(self):
        RadarAIReviewTests.setUp(self)
        mode=patch.object(technical_radar,'enabled',return_value=False);mode.start();self.addCleanup(mode.stop)

    def test_all_three_legacy_groups_share_one_task_and_worker(self):
        self.seed()
        KI.portfolio_save(self.store,[{'ticker':'AAA','shares':10,'entry_price':1.}])
        with self.store.transaction() as c:
            c.execute('CREATE TABLE ki_top5_follow(ticker TEXT PRIMARY KEY,status TEXT,first_at TEXT,last_at TEXT)')
            c.execute("INSERT INTO ki_top5_follow VALUES('AAA','FOLLOWING',?,?)",(self.now.isoformat(),self.now.isoformat()))
            c.execute("INSERT INTO large_movement_cases VALUES('AAA','WATCHING',?,?,?,1.2,'USD','{}',NULL,NULL,NULL)",
                      (self.now.isoformat(),self.now.isoformat(),self.now.isoformat()))
        self.assertEqual(self.schedule(),1)
        self.assertEqual(set(json.loads(self.rows_jobs()[0]['packet'])['selection']['roles']),{'TOP5','LARGE','PORTFOLIO'})
        self.assertEqual(self.schedule(),0)
        self.assertTrue(KI.service_work_due(self.store,'analysis',self.now))
        with patch('radar_ai.process_once',return_value=True) as worker:
            self.assertTrue(KI.process_analysis_once(self.store,{'OPENAI_API_KEY':'fixture'}))
            worker.assert_called_once()

    def test_unselected_companies_do_not_enter_ai_queue(self):
        self.seed('OTHER',score=100)
        self.seed('HELD',score=10)
        KI.portfolio_save(self.store,[{'ticker':'HELD','shares':1,'entry_price':1.}])
        self.assertEqual(self.schedule(),1)
        self.assertEqual([r['ticker'] for r in self.rows_jobs()],['HELD'])


if __name__=='__main__':unittest.main()
