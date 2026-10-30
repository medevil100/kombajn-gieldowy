"""Real SQLite and panel tests: lossless storage and bounded age retention, offline."""
import base64
import copy
from contextlib import closing
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
import zlib

import KI
import observation_storage as storage
import compact_observations
import cleanup_storage_20261030 as cleanup_tool
import sl_tp
import test_sl_tp_20261027 as fixtures
import tracking_view
import test_ab_contract as ai_fixtures


class ObservationStorageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'source.sqlite3'
        self.store = KI.Store(self.path)
        self.snapshot, self.now = fixtures.TradePlanTests().sample()
        self.snapshot.update(candle_time=self.now.replace(minute=0).isoformat(),
                             candle_end=(self.now+timedelta(hours=1)).isoformat(),
                             candle_status='OPEN', volume=250., rvol=2., average_volume=125.,
                             ohlc={'open':9., 'high':11., 'low':8., 'close':10.},
                             previous_closed={'open':9.,'close':9.5},
                             price_matrix={'change_pct':3.})
        self.snapshot['carried_price_candles'] = [{'time':str(n),'note':'Cena przeniesiona — nie transakcja'} for n in range(100)]

    def insert(self, snapshot=None, ticker='AAA', interval='1h', acquired=None, encoded=True):
        snap = snapshot or self.snapshot
        with self.store.transaction() as c:
            c.execute('INSERT INTO observations(ticker,interval,candle_time,acquired_at,candle_status,payload) VALUES(?,?,?,?,?,?)',
                      (ticker,interval,snap['candle_time'],acquired or self.now.isoformat(),'OPEN',
                       storage.encode_observation(snap) if encoded else KI.json_text(snap)))

    def test_lossless_roundtrip_preserves_unicode_numbers_and_entire_history(self):
        before = copy.deepcopy(self.snapshot)
        packed = storage.encode_observation(self.snapshot)
        self.assertEqual(storage.loads(packed), before)
        self.assertEqual(self.snapshot, before)
        self.assertLess(len(packed), len(KI.json_text(before)) * .6)
        self.assertIn(storage.MARKER, packed)
        self.assertEqual(KI.load_payload(packed), before)

    def test_legacy_payload_and_unrelated_json_still_work(self):
        for value in (self.snapshot, {'query':'źródła — GPW'}, [1,None,False], None):
            raw = json.dumps(value)
            self.assertEqual(storage.loads(raw), value)
        self.assertEqual(storage.loads(storage.encode_observation({})), {})

    def test_corrupt_or_oversized_history_fails_closed(self):
        packed = json.loads(storage.encode_observation(self.snapshot))
        packed['chart_history']['sha256'] = 'wrong'
        with self.assertRaises(ValueError): storage.loads(json.dumps(packed))
        packed['chart_history']['size'] = storage.MAX_HISTORY_BYTES + 1
        with self.assertRaises(ValueError): storage.loads(json.dumps(packed))
        packed['chart_history']['size'] = 10
        packed['chart_history'][storage.MARKER] = base64.b64encode(zlib.compress(b'x'*100000)).decode()
        with self.assertRaises(ValueError): storage.loads(json.dumps(packed))

    def test_sql_market_fields_remain_queryable_and_standalone_read_restores_levels(self):
        self.insert()
        with self.store.connection() as c:
            self.assertEqual(c.execute("SELECT json_extract(payload,'$.price') FROM observations").fetchone()[0],10.)
        restored = KI.portfolio_snapshot(self.store, 'AAA')
        self.assertEqual(restored['chart_history'], self.snapshot['chart_history'])
        self.assertEqual(sl_tp.build_plan(restored,3,self.now), sl_tp.build_plan(self.snapshot,3,self.now))
        self.assertEqual(tracking_view.level_view(restored,3,self.now)['plan']['sl'], 7.75)
        self.assertEqual(KI.portfolio_avg_volume_1m(restored), KI.portfolio_avg_volume_1m(self.snapshot))
        self.assertEqual(KI.gpt_chat_context(self.store,'AAA')['snapshot']['price'],10.)

    def test_actual_scanner_write_uses_compression_and_keeps_input_unchanged(self):
        snap = copy.deepcopy(self.snapshot)
        before = copy.deepcopy(snap)
        KI.detect_market(self.store,snap)
        with self.store.connection() as c:
            raw = c.execute('SELECT payload FROM observations').fetchone()[0]
        self.assertIn(storage.MARKER,raw)
        self.assertEqual(KI.load_payload(raw)['chart_history'],snap['chart_history'])
        self.assertEqual(snap,before)

    def test_ai_prompt_is_identical_for_plain_and_restored_observation(self):
        fixture=ai_fixtures.EtapAB()
        fixture.setUp()
        evidence=copy.deepcopy(fixture.evidence)
        plain=KI.event_analysis_request(evidence,fixture.context)
        evidence['snapshot']=storage.loads(storage.encode_observation(evidence['snapshot']))
        self.assertEqual(KI.event_analysis_request(evidence,fixture.context),plain)

    def test_tracking_query_restores_compressed_history_and_preserves_original_anchor(self):
        self.insert()
        original=copy.deepcopy(self.snapshot)
        original['price_matrix']={'anchor_price':8.,'change_pct':3.}
        with self.store.transaction() as c:
            c.execute('INSERT INTO opportunities VALUES(?,?,?,?,?,?,?,?,?)',
                      ('seq','AAA',self.snapshot['candle_time'],self.snapshot['candle_end'],
                       'SELECTED','cycle',KI.json_text({'snapshot':original}),
                       self.now.isoformat(),self.now.isoformat()))
        with self.store.connection() as c:before=list(c.iterdump())
        with patch.object(KI,'service_http',side_effect=AssertionError('paid API')):
            rows=KI.tracking_confirmed_opportunities(self.store,now=self.now)
        self.assertEqual(rows[0]['anchor_price'],8.)
        self.assertEqual(rows[0]['levels']['plan']['sl'],7.75)
        with self.store.connection() as c:self.assertEqual(before,list(c.iterdump()))

    def test_portfolio_panel_uses_packed_history_without_writes_or_api(self):
        start=self.now.replace(minute=0,second=0,microsecond=0)
        self.snapshot.update(candle_time=start.isoformat(),candle_end=(start+timedelta(hours=1)).isoformat())
        KI.portfolio_save(self.store,[{'ticker':'AAA','sl':1.2,'tp':2.5,'direction':'long',
                                      'sl_fired_at':None,'tp_fired_at':None}])
        self.insert()
        with self.store.connection() as c: before=list(c.iterdump())
        from streamlit.testing.v1 import AppTest
        script='import KI\nfrom pathlib import Path\nKI.render_portfolio(KI.Store(Path('+repr(str(self.path))+')))'
        import portfolio_view
        with patch.object(KI,'service_http',side_effect=AssertionError('paid API')),patch.object(KI,'fetch_market',side_effect=AssertionError('Yahoo')),patch.object(portfolio_view,'cards_html',wraps=portfolio_view.cards_html) as renderer:
            app=AppTest.from_string(script).run(timeout=30)
            self.assertEqual(len(app.exception),0)
            self.assertEqual(renderer.call_args.args[0][0]['_analysis_levels']['plan']['sl'],7.75)
        with self.store.connection() as c: self.assertEqual(before,list(c.iterdump()))

    def test_retention_preserves_latest_two_per_ticker_interval_and_all_other_tables(self):
        old=(self.now-timedelta(days=120)).isoformat()
        for ticker,interval,count in (('AAA','1h',5),('AAA','1d',2),('BBB','1h',1)):
            for _ in range(count): self.insert(ticker=ticker,interval=interval,acquired=old)
        self.insert(ticker='CCC',acquired=self.now.isoformat())
        with self.store.transaction() as c:
            c.execute("INSERT INTO events VALUES('saved','AAA','1h',?,?)",(old,KI.json_text({'snapshot':self.snapshot})))
            saved=c.execute('SELECT payload FROM events').fetchone()[0]
            self.assertEqual(storage.prune_observations(c,90,self.now),3)
            self.assertEqual(c.execute('SELECT payload FROM events').fetchone()[0],saved)
            counts=dict(c.execute('SELECT ticker,COUNT(*) FROM observations GROUP BY ticker'))
            self.assertEqual(counts,{'AAA':4,'BBB':1,'CCC':1})
        with self.store.transaction() as c: self.assertEqual(storage.prune_observations(c,90,self.now),0)

    def test_retention_is_batched_and_does_not_delete_boundary_recent_or_invalid_dates(self):
        old=(self.now-timedelta(days=120)).isoformat()
        for _ in range(8): self.insert(acquired=old)
        for at in ((self.now-timedelta(days=90)).isoformat(),self.now.isoformat(),'unknown'):
            self.insert(ticker='CCC',acquired=at)
        with self.store.transaction() as c:
            self.assertEqual(storage.prune_observations(c,90,self.now,batch_size=2),2)
            self.assertEqual(storage.prune_observations(c,90,self.now,batch_size=2),0)
            self.assertEqual(storage.prune_observations(c,90,self.now+timedelta(minutes=15),batch_size=2),2)
            self.assertEqual(c.execute("SELECT COUNT(*) FROM observations WHERE ticker='CCC'").fetchone()[0],3)

    def test_retention_rolls_back_with_parent_transaction(self):
        for _ in range(5): self.insert(acquired=(self.now-timedelta(days=120)).isoformat())
        with self.assertRaises(RuntimeError):
            with self.store.transaction() as c:
                self.assertEqual(storage.prune_observations(c,90,self.now),3)
                raise RuntimeError('abort')
        with self.store.connection() as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM observations').fetchone()[0],5)
            self.assertIsNone(c.execute("SELECT 1 FROM runtime WHERE key='observation_retention'").fetchone())

    def test_offline_compaction_preserves_all_records_and_never_changes_source(self):
        for _ in range(8): self.insert(encoded=False)
        with self.store.transaction() as c:
            c.execute("INSERT INTO events VALUES('reserved','AAA','1h',?,?)",(self.now.isoformat(),KI.json_text({'snapshot':self.snapshot})))
        with self.store.connection() as src:
            before=list(src.iterdump())
            destination=self.path.with_name('compact.sqlite3')
            count=compact_observations._copy_and_compact(src,destination,8,lambda *a,**k:None)
            self.assertEqual(count,8)
            self.assertEqual(before,list(src.iterdump()))
        with closing(sqlite3.connect(destination)) as dst:
            for (raw,) in dst.execute('SELECT payload FROM observations'):
                self.assertEqual(storage.loads(raw),self.snapshot)
            self.assertEqual(dst.execute('PRAGMA quick_check').fetchone()[0],'ok')
        with self.assertRaises(ValueError):compact_observations.compact(self.path,destination)

    def test_compaction_default_is_read_only(self):
        destination=self.path.with_name('unused.sqlite3')
        compact_observations.compact(self.path,destination,progress=lambda *a,**k:None)
        self.assertFalse(destination.exists())

    def cleanup_fixture(self):
        root=Path(self.tmp.name)/'ki2'
        for relative in cleanup_tool.REMOVE:
            path=root/relative
            path.parent.mkdir(parents=True,exist_ok=True)
            path.write_bytes(b'identified stale data')
        for name in cleanup_tool.RETAIN:
            with closing(sqlite3.connect(root/'backups'/name)) as db:
                db.execute('CREATE TABLE observations(id INTEGER)')
                db.execute('INSERT INTO observations VALUES(1)')
                db.commit()
        (root/'KI.matrix.sqlite3').write_bytes(b'live database must remain untouched')
        (root/'backups'/'another.partial').write_bytes(b'unidentified file must remain untouched')
        return root

    def test_cleanup_only_removes_allowlisted_files_after_both_backups_pass(self):
        root=self.cleanup_fixture()
        silent=lambda *a,**k:None
        self.assertEqual(cleanup_tool.cleanup(root,progress=silent),0)
        for path in cleanup_tool.REMOVE:self.assertTrue((root/path).exists())
        self.assertGreater(cleanup_tool.cleanup(root,True,silent),0)
        for path in cleanup_tool.REMOVE:self.assertFalse((root/path).exists())
        for name in cleanup_tool.RETAIN:self.assertTrue((root/'backups'/name).exists())
        self.assertEqual((root/'KI.matrix.sqlite3').read_bytes(),b'live database must remain untouched')
        self.assertTrue((root/'backups'/'another.partial').exists())

    def test_cleanup_bad_backup_refuses_all_deletions(self):
        root=self.cleanup_fixture()
        (root/'backups'/cleanup_tool.RETAIN[-1]).write_bytes(b'not a database')
        with self.assertRaises(sqlite3.DatabaseError):
            cleanup_tool.cleanup(root,True,lambda *a,**k:None)
        for path in cleanup_tool.REMOVE:self.assertTrue((root/path).exists())

    def test_compaction_interruption_keeps_source_unchanged(self):
        self.insert(encoded=False)
        with self.store.connection() as src:
            before=list(src.iterdump())
            with patch.object(compact_observations,'encode_observation',side_effect=RuntimeError('interrupted')):
                with self.assertRaises(RuntimeError):
                    compact_observations._copy_and_compact(src,self.path.with_name('interrupted.sqlite3'),1,lambda *a,**k:None)
            self.assertEqual(before,list(src.iterdump()))


if __name__ == '__main__':
    unittest.main()
