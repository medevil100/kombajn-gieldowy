import copy
import io
import json
import sqlite3
import tempfile
import unittest
from datetime import datetime,timedelta,timezone
from pathlib import Path
import KI
import sl_tp
import production_ops
import test_price_matrix as matrix_fixture
import test_sl_tp_20261027 as level_fixture


class TopTenTests(unittest.TestCase):
    def test_mirrored_up_down_receive_equal_directional_scores(self):
        now=datetime(2026,10,8,10,tzinfo=timezone.utc)
        scores=[]
        for direction in (1,-1):
            s=KI.opportunity_test_snapshot(now,'AAA',price=100+4*direction,rvol=3)
            s['ohlc']={'open':100,'high':105 if direction>0 else 101,'low':99 if direction>0 else 95}
            s['price_matrix']={'change_pct':4*direction,'state':'CONFIRMED','anchor_price':100,'anchor_at':now.isoformat()}
            s['indicators'].update(last_macd_hist=direction,ma_fast=100,plus_di=30 if direction>0 else 10,minus_di=10 if direction>0 else 30)
            p={**s,'acquired_at':(now-timedelta(minutes=1)).isoformat(),'price':100+3*direction,'volume':s['volume']-1}
            row=KI.opportunity_local_rank(s,p);scores.append(row['score'])
            self.assertEqual(row['score_direction'],'WZROST' if direction>0 else 'SPADEK')
            self.assertNotIn('okazja',row['quality'].lower())
        self.assertEqual(scores[0],scores[1])

    def test_real_matrix_splits_ten_each_without_losing_other_candidates(self):
        f=matrix_fixture.PriceMatrixTests();f.setUp();self.addCleanup(f.tearDown)
        ticks=[side+str(n).zfill(2)+'.WA' for side in ('UP','DN') for n in range(12)]
        f.store.save_section('tickers',ticks)
        for ticker in ticks:
            KI._save_daily_history(f.store,ticker,[{'session_date':'2026-10-07','status':'CLOSED','open':1.,'high':1.,'low':1.,'close':1.,'volume':1000}],f.anchor_time)
            for minutes in (0,15,30,45):
                s=f.snapshot(1. if minutes==0 else 1.04 if ticker.startswith('UP') else .96,minutes,ticker)
                d=KI.detect_market(f.store,s,{'price_matrix_enabled':True});s['price_matrix']=d['price_matrix'];KI.record_opportunity(f.store,s,'cycle',f.anchor_time+timedelta(minutes=minutes))
        rank=KI.load_growth_ranking(f.store,f.anchor_time+timedelta(minutes=45))
        self.assertEqual((len(rank['up']),len(rank['down'])),(10,10))
        self.assertEqual((rank['up_count'],rank['down_count']),(12,12))
        self.assertTrue(all(r['change_pct']>0 for r in rank['up']))
        self.assertTrue(all(r['change_pct']<0 for r in rank['down']))

    def test_downward_movement_has_levels_without_buy_or_short_plan(self):
        s,now=level_fixture.TradePlanTests().sample();p=sl_tp.build_plan(s,-3,now)
        self.assertEqual(p['status'],'UNAVAILABLE');self.assertEqual(p['side'],'NONE')
        self.assertIn('Wsparcie 8,0000',sl_tp.movement_space_line(p))
        self.assertIn('opór 12,0000',sl_tp.movement_space_line(p))
        self.assertNotIn('sl',p)

    def test_incomplete_source_is_diagnostic_not_model_evidence(self):
        ctx={'sources':[{'id':'S1','title':'snippet','content':'partial','content_complete':False},
                        {'id':'S2','content':'full','content_complete':True}], 'excluded':0}
        before=copy.deepcopy(ctx);clean=KI.complete_ai_sources(ctx)
        self.assertEqual([s['id'] for s in clean['sources']],['S2'])
        self.assertEqual(clean['incomplete_sources'][0]['id'],'S1');self.assertEqual(ctx,before)
        self.assertEqual(clean['excluded'],1)

    def test_automatic_research_context_does_not_duplicate_raw_provider_response(self):
        response={'request_id':'r','results':[],'raw_response':{'large':'provider copy'}}
        snapshot=KI.opportunity_test_snapshot(datetime(2026,10,8,10,tzinfo=timezone.utc),'AAA')
        context=KI.r1_research_sources(response,snapshot['acquired_at'],snapshot)
        self.assertNotIn('raw_response',context)
        self.assertEqual(context['raw_response_ref']['table'],'research_requests')

    def test_log_rotation_preserves_unicode_and_is_bounded(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'scanner.log';log=production_ops.ProcessLog(path,max_bytes=160,backups=2)
            log.attach(io.BytesIO(('żółć test\n'*50).encode('utf-8')),'scanner pid=1');log.close()
            self.assertTrue(path.exists());self.assertTrue(Path(str(path)+'.1').exists())
            self.assertLessEqual(len(list(Path(folder).glob('scanner.log*'))),3)
            self.assertIn('żółć',path.read_text(encoding='utf-8'))

    def test_old_cycles_are_closed_but_active_cycle_is_preserved(self):
        c=sqlite3.connect(':memory:');self.addCleanup(c.close)
        c.execute('create table cycles(id text,started_at text,finished_at text,status text,payload text)')
        c.executemany('insert into cycles values(?,?,NULL,?,?)',[('old','2026-10-13','RUNNING','{}'),('current','2026-10-27','RUNNING','{}')])
        self.assertEqual(production_ops.close_old_cycles(c,'2026-10-26','2026-10-27'),['old'])
        self.assertEqual(c.execute("select status from cycles where id='current'").fetchone()[0],'RUNNING')

    def test_quality_metrics_include_versions_filters_and_actual_usage(self):
        with tempfile.TemporaryDirectory() as folder:
            store=KI.Store(Path(folder)/'test.sqlite3')
            with store.transaction() as c:
                c.execute('insert into events values(?,?,?,?,?)',('e','AAA','1h',KI.utc_now(),'{}'))
                c.execute('insert into analysis_jobs(event_id,state,context,result,updated_at) values(?,?,?,?,?)',
                          ('e','DONE',json.dumps({'analysis_manifest':{'version':3}}),json.dumps({'analysis':{'quality_issues':['assessment: test']},'provider':{'usage':{'total_tokens':123}}}),KI.utc_now()))
            with store.connection() as c:m=production_ops.quality_metrics(c)
            self.assertEqual(m['versions'][0]['DONE'],1);self.assertEqual(m['tokens']['total_tokens'],123)
            self.assertEqual(m['usage_records'],1)


if __name__=='__main__':unittest.main()
