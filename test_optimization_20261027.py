"""Regresje audytu: rzeczywista SQLite i wątki; bez sieci i płatnych API."""
import concurrent.futures
import json
import sqlite3
import tempfile
import threading
from contextlib import closing
import unittest
from datetime import timedelta
from pathlib import Path
import KI
import tavily_cli_adapter as adapter
from migrate_optimization_20261027 import archive_orphan_rejections
from test_repair_20261024 import NOW


class OptimizationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.store=KI.Store(Path(self.temp.name)/'test.sqlite3')

    def test_portfolio_retry_is_not_claimed_before_due_and_attempts_unchanged(self):
        due=NOW+timedelta(minutes=5)
        with self.store.transaction() as c:
            c.execute('INSERT INTO events VALUES(?,?,?,?,?)',('e','AAA.WA','1h',NOW.isoformat(),'{}'))
            c.execute('INSERT INTO outbox(id,event_id,kind,message,status,next_attempt_at,created_at) VALUES(?,?,?,?,?,?,?)',('m','e','PORTFOLIO_ALERT','Test','PENDING',due.isoformat(),NOW.isoformat()))
        self.assertIsNone(KI.claim_delivery(self.store,now=NOW))
        self.assertIsNone(KI.claim_delivery(self.store,'m',now=NOW))
        with self.store.connection() as c:self.assertEqual(c.execute('SELECT attempts FROM outbox').fetchone()[0],0)
        self.assertEqual(KI.claim_delivery(self.store,'m',now=due)['id'],'m')

    def test_idle_queue_check_respects_due_time_without_claiming(self):
        self.assertFalse(KI.service_work_due(self.store,'analysis',NOW))
        self.assertFalse(KI.service_work_due(self.store,'telegram',NOW))
        due=NOW+timedelta(minutes=5)
        with self.store.transaction() as c:
            c.execute('INSERT INTO events VALUES(?,?,?,?,?)',('e','AAA.WA','1h',NOW.isoformat(),'{}'))
            c.execute('INSERT INTO analysis_jobs(event_id,state,next_attempt_at,updated_at) VALUES(?,?,?,?)',('e','PENDING_AI',due.isoformat(),NOW.isoformat()))
        self.assertFalse(KI.service_work_due(self.store,'analysis',NOW))
        self.assertTrue(KI.service_work_due(self.store,'analysis',due))
        with self.store.connection() as c:self.assertEqual(c.execute('SELECT state FROM analysis_jobs').fetchone()[0],'PENDING_AI')

    def test_portfolio_freshness_rejects_stale_weekend_carried_and_future(self):
        snap=KI.opportunity_test_snapshot(NOW,'STX.WA')
        self.assertTrue(KI.portfolio_price_status(snap,NOW)[0])
        for change in ({'acquired_at':(NOW-timedelta(seconds=901)).isoformat()},
                       {'acquired_at':(NOW+timedelta(seconds=1)).isoformat()},
                       {'latest_price_origin':'carried_previous_close'}, {'volume':0.},
                       {'candle_end':snap['candle_time']}):
            self.assertFalse(KI.portfolio_price_status({**snap,**change},NOW)[0])
        self.assertFalse(KI.portfolio_price_status(snap,NOW+timedelta(days=5))[0])

    def observation(self,snap):
        with self.store.transaction() as c:
            c.execute('INSERT INTO observations(ticker,interval,candle_time,acquired_at,candle_status,payload) VALUES(?,?,?,?,?,?)',
                      (snap['ticker'],snap['interval'],snap['candle_time'],snap['acquired_at'],snap['candle_status'],KI.json_text(snap)))

    def test_stale_price_never_triggers_or_rearms_sl_and_fresh_price_deduplicates(self):
        KI.portfolio_save(self.store,[{'ticker':'STX.WA','sl':110.,'tp':None,'direction':'long','sl_fired_at':None,'tp_fired_at':None}])
        snap=KI.opportunity_test_snapshot(NOW,'STX.WA',105.)
        self.observation({**snap,'acquired_at':(NOW-timedelta(hours=1)).isoformat()})
        self.assertEqual(KI.portfolio_check_alerts(self.store,now=NOW),0)
        self.observation(snap)
        self.assertEqual(KI.portfolio_check_alerts(self.store,now=NOW),1)
        self.assertEqual(KI.portfolio_check_alerts(self.store,now=NOW),0)
        self.observation({**snap,'price':120.,'acquired_at':(NOW-timedelta(hours=1)).isoformat()})
        KI.portfolio_check_alerts(self.store,now=NOW)
        self.assertIsNotNone(KI.portfolio_get(self.store)[0]['sl_fired_at'])
        with self.store.connection() as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM outbox').fetchone()[0],1)
            self.assertIn('Odczyt:',c.execute('SELECT message FROM outbox').fetchone()[0])

    def test_timeout_never_spawns_duplicate_or_unbounded_background_work(self):
        release=threading.Event()
        try:
            for key in ('audit-one','audit-two'):
                with self.assertRaises(KI.MarketDataUnavailable) as error:
                    KI.bounded_market_operation(lambda:release.wait(5),key,.01)
                self.assertEqual(error.exception.code,'TIMEOUT')
            with self.assertRaises(KI.MarketDataUnavailable) as error:KI.bounded_market_operation(lambda:True,'audit-one',1)
            self.assertEqual(error.exception.code,'FETCH_IN_PROGRESS')
            with self.assertRaises(KI.MarketDataUnavailable) as error:KI.bounded_market_operation(lambda:True,'audit-three',1)
            self.assertEqual(error.exception.code,'FETCH_CAPACITY')
        finally:
            with KI._market_fetch_lock:tasks=list(KI._market_fetch_tasks.values())
            release.set();concurrent.futures.wait(tasks,timeout=5)
        self.assertTrue(KI.bounded_market_operation(lambda:True,'audit-three',1))

    def test_extract_only_considers_eligible_sources_and_counts_no_request_without_key(self):
        response={'results':[{'url':'https://example.org/a','content_origin':'search_snippet'},
                             {'url':'https://example.org/b','content_origin':'search_snippet'}]}
        adapter.enrich_search_response(response,'',set())
        self.assertEqual(response['extract_diagnostics']['status'],'NOT_NEEDED')
        adapter.enrich_search_response(response,'',{'https://example.org/b'})
        self.assertEqual(response['extract_diagnostics']['requested_count'],1)
        self.assertEqual(response['extract_diagnostics']['attempted_count'],0)
        self.assertEqual(adapter.MAX_EXTRACT_URLS,8)

    def test_latest_index_avoids_sort_and_keeps_time_index(self):
        with self.store.connection() as c:
            plan=' '.join(str(tuple(r)) for r in c.execute("EXPLAIN QUERY PLAN SELECT payload FROM observations WHERE ticker='AAA' AND interval='1h' ORDER BY id DESC LIMIT 2"))
            self.assertIn('observation_latest',plan)
            self.assertNotIn('TEMP B-TREE',plan)
            self.assertIn('observation_lookup',{r[1] for r in c.execute("PRAGMA index_list('observations')")})

    def test_orphan_archival_preserves_full_record_and_is_idempotent(self):
        raw=('old','missing','Historyczny błąd',json.dumps({'full':['raw','response']}),NOW.isoformat())
        with closing(sqlite3.connect(self.store.path)) as c:
            with c:c.execute('INSERT INTO analysis_rejections VALUES(?,?,?,?,?)',raw)
        self.assertEqual(archive_orphan_rejections(self.store),1)
        self.assertEqual(archive_orphan_rejections(self.store),0)
        with self.store.connection() as c:
            saved=c.execute('SELECT id,event_id,reason,payload,created_at FROM archived_analysis_rejections').fetchone()
            self.assertEqual(tuple(saved),raw)
            self.assertEqual(c.execute('PRAGMA foreign_key_check').fetchall(),[])


if __name__=='__main__':unittest.main()
