"""Aktualność diagnostyki: SQLite i jawny czas, bez połączeń usług."""
import os
import tempfile
import unittest
from pathlib import Path
from datetime import datetime, timedelta, timezone
import KI


class ServiceStatusTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store=KI.Store(Path(self.tmp.name)/'status.sqlite3')
        self.now=datetime(2026,10,24,12,tzinfo=timezone.utc)

    def scanner(self,pid=None,at=None,status='RUNNING'):
        with self.store.transaction() as c:
            c.execute('INSERT OR REPLACE INTO runtime VALUES(?,?,?)',('scanner',KI.json_text(
                {'pid':pid or os.getpid(),'status':status}),(at or self.now).isoformat()))

    def test_old_ok_is_not_current_provider_confirmation(self):
        notice=KI.service_runtime_notice('service_analysis',(self.now-timedelta(days=3)).isoformat(),'OK',self.now)
        self.assertFalse(notice['fresh'])
        self.assertIn('nieaktualny',notice['message'])
        self.assertIn('nie jest bieżącym testem',notice['message'])

    def test_legacy_timezone_unknown_is_explicit_not_guessed(self):
        notice=KI.service_runtime_notice('service_telegram','2026-10-21 15:07:03','OK',self.now)
        self.assertFalse(notice['fresh'])
        self.assertIn('archiwalny',notice['message'])

    def test_recent_diagnostic_is_not_presented_as_provider_test(self):
        notice=KI.service_runtime_notice('service_analysis',self.now.isoformat(),'OK',self.now)
        self.assertTrue(notice['fresh'])
        self.assertIn('nie jest bieżącym testem',notice['message'])
        self.assertFalse(KI.service_runtime_notice('service_analysis',(self.now+timedelta(seconds=1)).isoformat(),'OK',self.now)['fresh'])

    def test_heartbeat_requires_current_scanner_and_matching_pid(self):
        KI.record_service_worker_health(self.store,'analysis','READY',self.now)
        self.assertEqual(KI.load_service_worker_health(self.store,self.now)[0]['status'],'UNCONFIRMED')
        self.scanner(pid=os.getpid()+1)
        self.assertEqual(KI.load_service_worker_health(self.store,self.now)[0]['status'],'UNCONFIRMED')
        self.scanner()
        self.assertEqual(KI.load_service_worker_health(self.store,self.now)[0]['status'],'READY')
        self.assertEqual(KI.load_service_worker_health(self.store,self.now+timedelta(seconds=31))[0]['status'],'UNCONFIRMED')

    def test_heartbeat_never_erases_saved_provider_error(self):
        self.scanner()
        with self.store.transaction() as c:
            c.execute('INSERT INTO runtime VALUES(?,?,?)',('service_analysis',KI.json_text({'status':'ERROR','error':'Błąd źródłowy'}),self.now.isoformat()))
        KI.record_service_worker_health(self.store,'analysis','READY',self.now)
        errors,notices,problems=KI.service_runtime_diagnostics(KI.load_service_runtime(self.store,{}))
        self.assertEqual(errors[0][2],'Błąd źródłowy')
        self.assertEqual(KI.load_service_worker_health(self.store,self.now)[0]['status'],'READY')

    def test_disabled_and_error_and_stopped_are_not_ready(self):
        self.scanner()
        for status in ('DISABLED','ERROR','STOPPED'):
            KI.record_service_worker_health(self.store,'telegram',status,self.now,error='problem' if status=='ERROR' else None)
            state=KI.load_service_worker_health(self.store,self.now)[1]
            self.assertEqual(state['status'],status)
            self.assertEqual(state['error'],'problem' if status=='ERROR' else None)

    def test_broken_heartbeat_does_not_crash_panel(self):
        self.scanner()
        with self.store.transaction() as c:
            c.execute('INSERT INTO runtime VALUES(?,?,?)',('worker_analysis','{broken',self.now.isoformat()))
        self.assertEqual(KI.load_service_worker_health(self.store,self.now)[0]['status'],'UNCONFIRMED')

    def test_worker_heartbeat_and_errors_survive_reopening_database(self):
        self.scanner()
        KI.record_service_worker_health(self.store,'analysis','ERROR',self.now,error='Brak klucza')
        reopened=KI.Store(self.store.path)
        self.assertEqual(KI.load_service_worker_health(reopened,self.now)[0]['error'],'Brak klucza')
        self.scanner(status='STOPPED')
        self.assertEqual(KI.load_service_worker_health(reopened,self.now)[0]['status'],'UNCONFIRMED')


if __name__=='__main__':unittest.main(verbosity=2)
