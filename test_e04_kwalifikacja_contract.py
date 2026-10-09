"""Etap E04: wszystkie potwierdzone ruchy rejestrowane bez limitu slotu.
Testy offline na rzeczywistym izolowanym SQLite; zero polaczen z siecia.
"""
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
import KI


class E04Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = KI.Store(Path(self.temp.name) / 'e04.sqlite3')
        self.now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
        # Existing legacy confirmation fixture; the production matrix is exercised
        # separately by test_e_integracja_contract.py and test_price_matrix.py.
        self.tickers = [f'XYZ{i}' for i in range(7)]
        self.store.save_section('tickers', self.tickers)

    def qualified(self, ticker, cycle):
        s = KI.opportunity_test_snapshot(self.now, ticker=ticker)
        KI.detect_market(self.store, s)
        KI.detect_market(self.store, s)
        result = KI.record_opportunity(self.store, s, cycle, self.now)
        self.assertEqual(result['state'], 'CONFIRMED')
        return result

    def counts(self):
        with self.store.connection() as c:
            return {t: c.execute('SELECT COUNT(*) FROM ' + t).fetchone()[0] for t in
                    ('opportunities', 'analysis_jobs', 'events', 'outbox')}

    def test_01_more_than_three_all_reserved_no_skip(self):
        for t in self.tickers:
            self.qualified(t, 'cycle')
        selected = KI.reserve_opportunities(self.store, 'cycle', self.now)
        self.assertEqual(len(selected), len(self.tickers))
        self.assertEqual({row['ticker'] for row in selected}, set(self.tickers))
        self.assertEqual(KI.reserve_opportunities(self.store, 'cycle', self.now), [])
        with self.store.connection() as c:
            states = dict(c.execute('SELECT state,COUNT(*) FROM opportunities GROUP BY state').fetchall())
            self.assertEqual(states, {'RESERVED': 7})
            self.assertEqual(c.execute('SELECT COUNT(*) FROM analysis_budgets').fetchone()[0], 0)

    def test_02_all_jobs_persist_atomically_without_duplicates(self):
        for t in self.tickers:
            self.qualified(t, 'cycle')
        selected = KI.reserve_opportunities(self.store, 'cycle', self.now)
        for item in selected:
            self.assertTrue(KI.queue_opportunity(self.store, item['sequence_id'], {}, False, self.now))
            self.assertFalse(KI.queue_opportunity(self.store, item['sequence_id'], {}, False, self.now))
        self.assertEqual(self.counts(), {'opportunities': 7, 'analysis_jobs': 7, 'events': 7, 'outbox': 0})
        with KI.Store(self.store.path).connection() as c:
            self.assertEqual(c.execute("SELECT COUNT(*) FROM analysis_jobs WHERE state='PENDING_CONTEXT'").fetchone()[0], 7)

    def test_03_legacy_skipped_limit_rejoins_if_still_confirmed(self):
        a = self.qualified('XYZ0', 'old')
        with self.store.transaction() as c:
            c.execute("UPDATE opportunities SET state='SKIPPED_LIMIT' WHERE sequence_id=?", (a['sequence_id'],))
        refreshed = KI.record_opportunity(self.store, KI.opportunity_test_snapshot(self.now, ticker='XYZ0'), 'new', self.now)
        self.assertEqual(refreshed['state'], 'CONFIRMED')
        self.assertEqual(len(KI.reserve_opportunities(self.store, 'new', self.now)), 1)
        with self.store.connection() as c:
            row=c.execute('SELECT state,cycle_id FROM opportunities WHERE sequence_id=?', (a['sequence_id'],)).fetchone()
            self.assertEqual(tuple(row), ('RESERVED', 'new'))

    def test_04_legacy_skip_not_revived_without_confirmation(self):
        a = self.qualified('XYZ0', 'old')
        with self.store.transaction() as c:
            c.execute("UPDATE opportunities SET state='SKIPPED_LIMIT' WHERE sequence_id=?", (a['sequence_id'],))
        stale = KI.opportunity_test_snapshot(self.now - timedelta(minutes=16), ticker='XYZ0')
        rejected = KI.record_opportunity(self.store, stale, 'new', self.now)
        self.assertEqual(rejected['state'], 'NOT_QUALIFIED')
        self.assertEqual(KI.reserve_opportunities(self.store, 'new', self.now), [])
        self.assertEqual(self.counts()['analysis_jobs'], 0)

    def test_05_restart_same_slot_does_not_block_new_confirmations(self):
        for t in self.tickers[:4]:
            self.qualified(t, 'first')
        self.assertEqual(len(KI.reserve_opportunities(self.store, 'first', self.now)), 4)
        for t in self.tickers[4:]:
            self.qualified(t, 'second')
        self.assertEqual(len(KI.reserve_opportunities(KI.Store(self.store.path), 'second', self.now)), 3)

    def test_06_early_candidates_not_sent_to_analyses(self):
        ticker='XYZ0'
        s=KI.opportunity_test_snapshot(self.now, ticker=ticker, price=104)
        KI.detect_market(self.store, s)
        KI.detect_market(self.store, s)
        self.assertEqual(KI.record_opportunity(self.store, s, 'cycle', self.now)['state'], 'CANDIDATE')
        self.assertEqual(KI.reserve_opportunities(self.store, 'cycle', self.now), [])
        self.assertEqual(self.counts()['analysis_jobs'], 0)


    def test_07_real_matrix_three_read_confirmations_all_eligible(self):
        base = datetime(2026, 10, 9, 12, 0, tzinfo=timezone.utc)
        cfg = {'price_matrix_enabled': True, 'auto_scan_interval': 15,
               'price_threshold_pct': 2.0}
        confirmed = []
        for ticker in self.tickers[:5]:
            latest = None
            for minute, price in ((2, 100.), (17, 103.), (32, 104.), (47, 105.)):
                at = base + timedelta(minutes=minute)
                snap = KI.opportunity_test_snapshot(at, ticker=ticker, price=price)
                snap['volume']=100000+(minute%60)
                detection = KI.detect_market(self.store, snap, cfg)
                latest = {**snap, 'price_matrix': detection['price_matrix']}
            self.assertEqual(detection['price_matrix']['state'], 'CONFIRMED')
            self.assertEqual(detection['price_matrix']['consecutive_reads'], 3)
            result = KI.record_opportunity(self.store, latest, 'matrix', base+timedelta(minutes=47))
            self.assertEqual(result['state'], 'CONFIRMED')
            confirmed.append(result['sequence_id'])
        selected = KI.reserve_opportunities(self.store, 'matrix', base+timedelta(minutes=47))
        self.assertEqual({r['sequence_id'] for r in selected}, set(confirmed))
        for r in selected:
            self.assertTrue(KI.queue_opportunity(self.store, r['sequence_id'], {}, False,
                                                 base+timedelta(minutes=47)))
        self.assertEqual(self.counts()['analysis_jobs'], 5)
        self.assertTrue(all(KI.Store(self.store.path).get_price_matrix(t)['anchor_price'] == 100
                            for t in self.tickers[:5]))


if __name__ == '__main__':
    unittest.main(verbosity=2)
