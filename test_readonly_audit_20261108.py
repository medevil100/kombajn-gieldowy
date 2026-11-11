"""Temporary SQLite fixtures only; no production access or network."""
import hashlib
import json
from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest

from ki2_readonly_audit import read_audit


class ReadOnlyAuditTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.path = Path(folder.name) / 'audit.sqlite3'
        self.at = '2026-11-09T15:00:00+00:00'
        self.end = '2026-11-09T15:01:00+00:00'
        with closing(sqlite3.connect(self.path)) as db, db:
            db.executescript('''
                CREATE TABLE runtime(key TEXT,updated_at TEXT,payload TEXT);
                CREATE TABLE cycles(status TEXT,started_at TEXT);
                CREATE TABLE events(id TEXT,created_at TEXT,payload TEXT);
                CREATE TABLE analysis_jobs(event_id TEXT,state TEXT,context TEXT,result TEXT);
                CREATE TABLE company_review_batches(state TEXT,created_at TEXT,payload TEXT);
                CREATE TABLE outbox(kind TEXT,status TEXT,created_at TEXT);
            ''')
            db.execute('INSERT INTO runtime VALUES(?,?,?)', ('scanner', self.at, '{"status":"RUNNING","pid":100}'))
            db.execute('INSERT INTO cycles VALUES(?,?)', ('OK', self.at))
            db.execute('INSERT INTO events VALUES(?,?,?)', ('one', self.at, '{"company_review_batch":"batch"}'))
            context = {'analysis_manifest': {'session_context': {'status': 'COMPLETE_TO_ASOF'}},
                       'private': 'DO_NOT_PUBLISH_PRIVATE_VALUE'}
            result = {'analysis': {'final_review': {'attention': 'INFORM'}, 'quality_issues': []},
                      'provider': {'usage': {'total_tokens': 120}, 'private': 'DO_NOT_PUBLISH_PRIVATE_VALUE'}}
            db.execute('INSERT INTO analysis_jobs VALUES(?,?,?,?)', ('one', 'DONE', json.dumps(context), json.dumps(result)))
            db.execute('INSERT INTO events VALUES(?,?,?)', ('old', '2026-11-06T15:00:00+00:00', '{}'))
            db.execute('INSERT INTO analysis_jobs VALUES(?,?,?,?)', ('old', 'FAILED', '{}', '{}'))
            db.execute('INSERT INTO company_review_batches VALUES(?,?,?)', ('READY', self.at,
                       '{"pool":[{"state":"ALREADY_REVIEWED"}],"diagnostics":[{"status":"QUEUED"}]}'))
            db.execute('INSERT INTO outbox VALUES(?,?,?)', ('FINAL_COMPANY_DIGEST', 'SENT', self.at))

    def test_counters_use_selected_events_and_do_not_publish_raw_material(self):
        report = read_audit(self.path, self.at, self.end)
        self.assertEqual(report['analysis_jobs'], {'DONE': 1})
        self.assertEqual(report['final_reviews']['session_coverage'], {'COMPLETE_TO_ASOF': 1})
        self.assertEqual(report['selection_reasons'], {'ALREADY_REVIEWED': 1})
        self.assertEqual(report['preparation'], {'QUEUED': 1})
        self.assertEqual(report['openai_recorded_usage']['total_tokens'], 120)
        self.assertEqual(report['runtime']['scanner']['age_seconds'], 60)
        self.assertNotIn('DO_NOT_PUBLISH_PRIVATE_VALUE', json.dumps(report))
        self.assertEqual(report['warnings'], [])

    def test_read_does_not_change_database_bytes_or_modification_time(self):
        before = hashlib.sha256(self.path.read_bytes()).hexdigest(), self.path.stat().st_mtime_ns
        read_audit(self.path, self.at, self.end)
        after = hashlib.sha256(self.path.read_bytes()).hexdigest(), self.path.stat().st_mtime_ns
        self.assertEqual(before, after)

    def test_missing_database_is_not_created(self):
        absent = self.path.with_name('absent.sqlite3')
        with self.assertRaises(FileNotFoundError):
            read_audit(absent, self.at, self.end)
        self.assertFalse(absent.exists())

    def test_invalid_time_and_partial_schema_are_explicit(self):
        with self.assertRaises(ValueError):
            read_audit(self.path, '2026-11-09T15:00:00', self.end)
        with self.assertRaises(ValueError):
            read_audit(self.path, self.end, self.at)
        other = self.path.with_name('older.sqlite3')
        with closing(sqlite3.connect(other)) as db, db:
            db.execute('CREATE TABLE legacy(id TEXT)')
        report = read_audit(other, self.at, self.end)
        self.assertIn('MISSING_TABLE:analysis_jobs', report['warnings'])


if __name__ == '__main__':
    unittest.main()
