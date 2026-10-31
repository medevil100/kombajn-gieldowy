"""Offline supervision, RO SQLite, mocked systemd/Telegram, Linux real flock tests."""
from contextlib import contextmanager
import copy
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
from types import SimpleNamespace
import tempfile
import subprocess
import sys
import unittest
from unittest.mock import patch

import KI
import ki2_guardian as guardian
import ki2_ops_guard as guard


class GuardianTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.folder=Path(self.tmp.name)
        self.path=self.folder/'KI.matrix.sqlite3'
        self.store=KI.Store(self.path)
        self.state=self.folder/'state.json'
        self.now=datetime(2026,10,31,18,10,tzinfo=timezone.utc)

    def report(self):
        runtime={k:{'updated_at':self.now.isoformat(),'pid':123,'status':'RUNNING' if k=='scanner' else 'READY'}
                 for k in ('scanner','worker_analysis','worker_telegram')}
        return {'at':self.now.isoformat(),'issues':[], 'facts':{
            'service':{'ActiveState':'active','Result':'success'},'uptime':3600,
            'backup':{'ActiveState':'inactive','Result':'success'},'timer':{'ActiveState':'active'},
            'disk_free':16*guardian.GIB,'db_bytes':3*guardian.GIB,'backup_age':14*3600,
            'runtime':runtime,'panel_ok':True,'cadence':15,'busy_jobs':0,
            'cycle':{'started_at':(self.now-timedelta(minutes=10)).isoformat(),
                     'finished_at':(self.now-timedelta(minutes=5)).isoformat(),'status':'OK'}}}

    def assessed(self,edit=None):
        report=self.report()
        if edit:edit(report['facts'])
        return guardian.assess(report,self.now)

    def test_weekend_healthy_old_prices_are_not_a_fault(self):
        report=self.assessed()
        self.assertEqual(report['status'],'HEALTHY')
        self.assertEqual(report['issues'],[])
        state,action,message=guardian.transition({},report,self.now.timestamp())
        self.assertEqual(action,'NONE');self.assertIsNone(message)

    def test_manual_pause_never_restarts_or_alerts(self):
        report=self.assessed(lambda f:f['service'].update(ActiveState='inactive'))
        state,action,message=guardian.transition({},report,self.now.timestamp())
        self.assertEqual(report['status'],'PAUSED')
        self.assertEqual(action,'NONE');self.assertIsNone(message)

    def test_backup_pause_suppresses_expected_panel_and_scanner_down(self):
        report=self.assessed(lambda f:(f['backup'].update(ActiveState='activating'),
                                       f.update(panel_ok=False,runtime={})))
        self.assertEqual(report['status'],'MAINTENANCE')
        self.assertEqual(report['issues'],[])

    def test_startup_grace_prevents_restart_loop(self):
        report=self.assessed(lambda f:f.update(uptime=60,panel_ok=False,runtime={}))
        self.assertEqual(report['status'],'GRACE')
        self.assertEqual(report['issues'],[])

    def test_operator_disabled_scanning_and_services_are_valid(self):
        def edit(f):
            f.update(cadence=0,cycle=None)
            f['runtime']['scanner']['status']='PAUSED'
            for kind in ('analysis','telegram'):f['runtime']['worker_'+kind]['status']='DISABLED'
        self.assertEqual(self.assessed(edit)['status'],'HEALTHY')

    def test_cycle_progress_is_checked_even_if_heartbeat_keeps_running(self):
        report=self.assessed(lambda f:f.update(cycle={'started_at':(self.now-timedelta(hours=1)).isoformat(),
                                                     'finished_at':None,'status':'RUNNING'}))
        self.assertIn('CYCLE_STUCK',{i['code'] for i in report['issues']})
        report=self.assessed(lambda f:f.update(cycle=None))
        self.assertIn('CYCLE_MISSING',{i['code'] for i in report['issues']})

    def test_long_but_bounded_cycle_is_valid(self):
        report=self.assessed(lambda f:f.update(cycle={'started_at':(self.now-timedelta(minutes=20)).isoformat(),
                                                     'finished_at':None,'status':'RUNNING'}))
        self.assertEqual(report['status'],'HEALTHY')

    def test_provider_outage_is_reported_without_restart_or_retry(self):
        report=self.assessed(lambda f:f.update(recent_cycle_statuses=['ERROR','RATE_LIMITED','ERROR']))
        state={}
        for _ in range(3):state,action,message=guardian.transition(state,report,self.now.timestamp())
        self.assertEqual(action,'NONE')
        self.assertIsNotNone(message)
        self.assertEqual({i['code'] for i in report['issues']},{'DATA_SOURCE_PROBLEM'})

    def test_worker_uses_pid_and_timestamp_evidence(self):
        def edit(f):
            f['runtime']['worker_analysis']['pid']=999
            f['runtime']['worker_telegram']['updated_at']=(self.now-timedelta(minutes=10)).isoformat()
        codes={i['code'] for i in self.assessed(edit)['issues']}
        self.assertEqual(codes,{'WORKER_ANALYSIS_STALE','WORKER_TELEGRAM_STALE'})

    def test_future_heartbeat_is_intervention_not_restart(self):
        report=self.assessed(lambda f:f['runtime']['scanner'].update(updated_at=(self.now+timedelta(hours=1)).isoformat()))
        state,action,_=guardian.transition({},report,self.now.timestamp())
        self.assertEqual(action,'BLOCKED_INTERVENTION')
        self.assertIn('CLOCK_INVALID',{i['code'] for i in report['issues']})

    def test_backup_disk_and_timer_faults_are_reported_without_restarting_ki(self):
        report=self.assessed(lambda f:(f.update(disk_free=2*guardian.GIB,backup_age=40*3600),
                                       f['backup'].update(Result='timeout'),f['timer'].update(ActiveState='inactive')))
        codes={i['code'] for i in report['issues']}
        self.assertEqual(codes,{'DISK_CRITICAL','BACKUP_STALE','BACKUP_FAILED','BACKUP_TIMER_OFF'})
        state,action,_=guardian.transition({},report,self.now.timestamp())
        self.assertEqual(action,'BLOCKED_INTERVENTION')

    def test_three_consecutive_failures_are_required(self):
        report=self.assessed(lambda f:f.update(panel_ok=False))
        state={}
        for n in range(3):
            state,action,message=guardian.transition(state,report,self.now.timestamp()+120*n)
            self.assertEqual(action,'RESTART_ELIGIBLE' if n==2 else 'NONE')
            self.assertEqual(message is not None,n==2)
        state,_,_=guardian.transition(state,self.assessed(),self.now.timestamp()+400)
        state,action,_=guardian.transition(state,report,self.now.timestamp()+500)
        self.assertEqual(action,'NONE')

    def test_active_jobs_block_restart_and_history_is_not_requeued(self):
        report=self.assessed(lambda f:f.update(panel_ok=False,busy_jobs=1))
        state={'failures':{'PANEL_DOWN':2}}
        _,action,_=guardian.transition(state,report,self.now.timestamp())
        self.assertEqual(action,'BLOCKED_INFLIGHT')

    def test_cooldown_and_two_attempts_per_rolling_day(self):
        report=self.assessed(lambda f:f.update(panel_ok=False))
        now=self.now.timestamp()
        for attempts in ([now-100],[now-8000,now-4000],[now+100]):
            state={'failures':{'PANEL_DOWN':2},'restarts':attempts}
            _,action,_=guardian.transition(state,report,now)
            self.assertEqual(action,'BLOCKED_LIMIT')
        state={'failures':{'PANEL_DOWN':2},'restarts':[now-90000,now-2000]}
        updated,action,_=guardian.transition(state,report,now)
        self.assertEqual(action,'RESTART_ELIGIBLE')
        self.assertEqual(len(updated['restarts']),1)

    def test_single_incident_then_recovery_after_two_good_checks(self):
        bad=self.assessed(lambda f:f.update(panel_ok=False));good=self.assessed();state={};messages=[]
        for report in [bad]*6+[good]*3:
            state,_,message=guardian.transition(state,report,self.now.timestamp())
            if message:messages.append(message)
        self.assertEqual(len(messages),2)
        self.assertTrue(messages[0].startswith('AWARIA'))
        self.assertIn('przywrócono',messages[1])

    def seed_database(self):
        with self.store.transaction() as db:
            for key,value in self.report()['facts']['runtime'].items():
                payload={**value,'error':'MUST NOT LEAK'}
                db.execute('INSERT INTO runtime VALUES(?,?,?)',(key,json.dumps(payload),self.now.isoformat()))
            db.execute('INSERT INTO cycles VALUES(?,?,?,?,?)',('cycle',(self.now-timedelta(minutes=10)).isoformat(),
                       self.now.isoformat(),'OK','{"huge":"DO NOT READ"}'))

    def test_real_sqlite_audit_is_read_only_and_excludes_payloads_and_errors(self):
        self.seed_database()
        with self.store.connection() as db:before=list(db.iterdump())
        facts=guardian.database_facts(self.path)
        self.assertEqual(facts['busy_jobs'],0)
        self.assertEqual(facts['runtime']['scanner']['pid'],123)
        self.assertNotIn('MUST NOT LEAK',json.dumps(facts))
        self.assertNotIn('DO NOT READ',json.dumps(facts))
        with self.store.connection() as db:self.assertEqual(before,list(db.iterdump()))

    def test_root_database_reader_uses_isolated_ubuntu_child(self):
        with patch.object(guardian,'is_root',return_value=True),patch.object(guardian.subprocess,'run',return_value=SimpleNamespace(returncode=0,stdout='{"busy_jobs":0}')) as child:
            self.assertEqual(guardian.database_facts(self.path),{'busy_jobs':0})
        command=child.call_args.args[0]
        self.assertEqual(command[0],'/usr/bin/systemd-run')
        self.assertIn('--internal-facts',command)
        for prop in ('User=ubuntu','Group=ubuntu','NoNewPrivileges=yes','ProtectSystem=strict',
                     'ProtectHome=read-only','ReadWritePaths=/home/ubuntu/ki2','RestrictSUIDSGID=yes'):
            self.assertIn('--property='+prop,command)
        self.assertIn('--collect',command)
        self.assertIn('--wait',command)
        self.assertIn('--pipe',command)
        self.assertNotIn('user',child.call_args.kwargs)
        self.assertNotIn('group',child.call_args.kwargs)
        self.assertNotIn('runuser',' '.join(command))

    def test_root_reader_units_have_unique_names_and_fixed_isolated_executable(self):
        with patch.object(guardian,'is_root',return_value=True),patch.object(guardian.subprocess,'run',return_value=SimpleNamespace(returncode=0,stdout='{"busy_jobs":0}')) as child:
            guardian.database_facts(self.path)
            guardian.database_facts(self.path)
        commands=[call.args[0] for call in child.call_args_list]
        names=[next(a for a in cmd if a.startswith('--unit=')) for cmd in commands]
        self.assertNotEqual(names[0],names[1])
        for cmd in commands:
            at=cmd.index('/usr/bin/python3')
            self.assertEqual(cmd[at+1],'-I')
            self.assertEqual(cmd[-2: ],['--db',str(self.path)])

    def test_root_child_error_exposes_only_bounded_type_not_stderr(self):
        reply=SimpleNamespace(returncode=1,stdout='{"status":"CHECK_FAILED","error_type":"OperationalError"}',stderr='SECRET PROVIDER KEY')
        with patch.object(guardian,'is_root',return_value=True),patch.object(guardian.subprocess,'run',return_value=reply):
            with self.assertRaises(guardian.DatabaseAuditUnavailable) as error:
                guardian.database_facts(self.path)
        self.assertEqual(error.exception.diagnostic,{'reason':'CHILD_FAILED','child_error_type':'OperationalError'})
        self.assertNotIn('SECRET',str(error.exception))

    def test_root_child_bad_json_schema_or_timeout_fails_closed(self):
        for reply in (SimpleNamespace(returncode=0,stdout='not JSON'),
                      SimpleNamespace(returncode=0,stdout='{}'),
                      SimpleNamespace(returncode=0,stdout='x'*70000)):
            with patch.object(guardian,'is_root',return_value=True),patch.object(guardian.subprocess,'run',return_value=reply):
                with self.assertRaises(guardian.DatabaseAuditUnavailable):guardian.database_facts(self.path)
        with patch.object(guardian,'is_root',return_value=True),patch.object(guardian.subprocess,'run',side_effect=PermissionError('secret')):
            with self.assertRaises(guardian.DatabaseAuditUnavailable) as error:guardian.database_facts(self.path)
        self.assertEqual(error.exception.diagnostic['child_error_type'],'PermissionError')

    def test_root_child_cause_reaches_safe_audit_report(self):
        with patch.object(guardian,'collect',side_effect=guardian.DatabaseAuditUnavailable('CHILD_FAILED','OperationalError')):
            report=guardian.run(self.path,self.state,now=self.now)
        self.assertEqual(report['diagnostic']['child_error_type'],'OperationalError')

    def test_collect_reads_status_not_market_history(self):
        self.seed_database()
        backups=self.folder/'backups';backups.mkdir()
        archive=backups/'ki2-20261031T033003608886Z.sqlite3';archive.write_bytes(b'archive')
        os.utime(archive,(self.now.timestamp()-3600,self.now.timestamp()-3600))
        def unit(name):
            return {'ActiveState':'inactive' if name=='ki2-backup.service' else 'active',
                    'Result':'success','ActiveEnterTimestampMonotonic':'1000000'}
        with self.store.connection() as db:before=list(db.iterdump())
        with patch.object(guardian,'system_unit',side_effect=unit),patch.object(guardian.time,'monotonic',return_value=10000),patch.object(guardian.shutil,'disk_usage',return_value=SimpleNamespace(free=16*guardian.GIB)),patch.object(guardian,'panel_health',return_value=True):
            report=guardian.collect(self.path,self.now)
        self.assertEqual(report['status'],'HEALTHY')
        self.assertEqual(report['facts']['backup_name'],archive.name)
        with self.store.connection() as db:self.assertEqual(before,list(db.iterdump()))

    def test_telegram_failure_never_exposes_token_or_exception(self):
        secrets=self.folder/'secrets.toml'
        token=str(12345678)+':'+('x'*35)
        secrets.write_text('TELEGRAM_BOT_TOKEN="'+token+'"\nTELEGRAM_CHAT_ID="1234"\n',encoding='utf-8')
        class Broken:
            def open(self,*args,**kwargs):raise RuntimeError(token)
        with patch.object(guardian,'opener',return_value=Broken()):
            result=guardian.notify_telegram('test',secrets)
        self.assertEqual(result,'UNCERTAIN')
        self.assertNotIn(token,result)

    def test_busy_ledger_counts_all_modes_but_ignores_failed_review_history(self):
        with self.store.transaction() as db:
            db.execute('INSERT INTO events VALUES(?,?,?,?,?)',('event','AAA','1h',self.now.isoformat(),'{}'))
            db.execute("INSERT INTO analysis_jobs(event_id,state,updated_at) VALUES('event','REVIEW_REQUIRED',?)",(self.now.isoformat(),))
            db.execute("INSERT INTO outbox(id,event_id,kind,message,status,created_at) VALUES('msg','event','ANALYSIS','x','UNCERTAIN',?)",(self.now.isoformat(),))
        self.assertEqual(guardian.database_facts(self.path)['busy_jobs'],0)
        with self.store.transaction() as db:
            db.execute("UPDATE analysis_jobs SET state='BUSY_AI'")
            db.execute("UPDATE outbox SET status='SENDING'")
            db.execute("INSERT INTO gpt_chat_turns(id,question,context,state,created_at) VALUES('chat','q','{}','REQUESTED',?)",(self.now.isoformat(),))
            db.execute("INSERT INTO deep_reports(id,ticker,state,created_at) VALUES('deep','AAA','QUEUED',?)",(self.now.isoformat(),))
        self.assertEqual(guardian.database_facts(self.path)['busy_jobs'],4)

    def test_check_never_changes_state_restarts_or_notifies(self):
        with patch.object(guardian,'collect',return_value=self.assessed()),patch.object(guardian,'notify_telegram',side_effect=AssertionError('Telegram')),patch.object(guardian.subprocess,'run',side_effect=AssertionError('systemctl')):
            self.assertEqual(guardian.run(self.path,self.state,False,True,True,self.now)['status'],'HEALTHY')
        self.assertFalse(self.state.exists())

    def test_unreadable_database_reports_intervention_with_no_restart(self):
        with patch.object(guardian,'collect',side_effect=RuntimeError('SECRET MUST NOT LEAK')):
            report=guardian.run(self.path,self.state,now=self.now)
        self.assertEqual(report['issues'][0]['code'],'AUDIT_UNAVAILABLE')
        self.assertNotIn('SECRET',json.dumps(report))

    @contextmanager
    def lease(self,acquired=True):
        yield acquired

    def ready_restart_state(self):
        self.state.write_text(json.dumps({'failures':{'PANEL_DOWN':2}}),encoding='utf-8')

    def test_exclusive_lease_prevents_restart_when_provider_is_running(self):
        self.ready_restart_state()
        with patch.object(guardian,'collect',return_value=self.assessed(lambda f:f.update(panel_ok=False))),patch.object(guardian,'exclusive_provider_lease',return_value=self.lease(False)),patch.object(guardian.subprocess,'run',side_effect=AssertionError('restart')):
            report=guardian.run(self.path,self.state,True,False,True,self.now)
        self.assertEqual(report['action'],'BLOCKED_PROVIDER_LEASE')

    def test_recheck_detects_new_busy_job_after_exclusive_lease(self):
        self.ready_restart_state()
        with patch.object(guardian,'collect',return_value=self.assessed(lambda f:f.update(panel_ok=False))),patch.object(guardian,'exclusive_provider_lease',return_value=self.lease()),patch.object(guardian,'system_unit',return_value={'ActiveState':'inactive'}),patch.object(guardian,'database_facts',return_value={'busy_jobs':1}),patch.object(guardian.subprocess,'run',side_effect=AssertionError('restart')):
            report=guardian.run(self.path,self.state,True,False,True,self.now)
        self.assertEqual(report['action'],'BLOCKED_INFLIGHT')

    def test_backup_race_is_rechecked_inside_restart_lease(self):
        self.ready_restart_state()
        with patch.object(guardian,'collect',return_value=self.assessed(lambda f:f.update(panel_ok=False))),patch.object(guardian,'exclusive_provider_lease',return_value=self.lease()),patch.object(guardian,'system_unit',return_value={'ActiveState':'activating'}),patch.object(guardian.subprocess,'run',side_effect=AssertionError('restart')):
            report=guardian.run(self.path,self.state,True,False,True,self.now)
        self.assertEqual(report['action'],'BLOCKED_BACKUP')

    def test_restart_budget_is_reserved_before_fixed_try_restart_command(self):
        self.ready_restart_state()
        def command(args,**kwargs):
            self.assertEqual(args,['/usr/bin/systemctl','try-restart','ki2.service'])
            self.assertEqual(len(json.loads(self.state.read_text())['restarts']),1)
            return SimpleNamespace(returncode=0)
        with patch.object(guardian,'collect',return_value=self.assessed(lambda f:f.update(panel_ok=False))),patch.object(guardian,'exclusive_provider_lease',return_value=self.lease()),patch.object(guardian,'system_unit',return_value={'ActiveState':'inactive'}),patch.object(guardian,'database_facts',return_value={'busy_jobs':0}),patch.object(guardian.subprocess,'run',side_effect=command):
            report=guardian.run(self.path,self.state,True,False,True,self.now)
        self.assertEqual(report['action'],'RESTART_REQUESTED')

    def test_unknown_notification_is_reserved_once_and_never_retried(self):
        self.ready_restart_state()
        def send(message,secrets):
            self.assertEqual(json.loads(self.state.read_text())['notification'],'ATTEMPT_RESERVED')
            return 'UNCERTAIN'
        with patch.object(guardian,'collect',return_value=self.assessed(lambda f:f.update(panel_ok=False))),patch.object(guardian,'notify_telegram',side_effect=send) as notify:
            guardian.run(self.path,self.state,True,True,False,self.now)
            guardian.run(self.path,self.state,True,True,False,self.now+timedelta(minutes=2))
        self.assertEqual(notify.call_count,1)

    def test_notification_disabled_is_quiet(self):
        self.ready_restart_state()
        with patch.object(guardian,'collect',return_value=self.assessed(lambda f:f.update(panel_ok=False))),patch.object(guardian,'notify_telegram',side_effect=AssertionError('Telegram')):
            guardian.run(self.path,self.state,True,False,False,self.now)

    def test_corrupted_state_fails_closed(self):
        self.state.write_text('not JSON',encoding='utf-8')
        with patch.object(guardian,'collect',return_value=self.assessed()),patch.object(guardian.subprocess,'run',side_effect=AssertionError('restart')):
            with self.assertRaises(ValueError):guardian.run(self.path,self.state,True,False,True,self.now)
        self.assertEqual(self.state.read_text(),'not JSON')

    def test_guard_blocks_before_claim_without_changing_jobs_or_calling_providers(self):
        with self.store.connection() as db:before=list(db.iterdump())
        with patch.object(guard,'provider_lease',side_effect=lambda:self.lease(False)),patch.object(KI,'service_http',side_effect=AssertionError('provider')):
            self.assertFalse(KI.process_analysis_once(self.store,{}))
        with patch.object(guard,'provider_lease',side_effect=lambda:self.lease(False)):
            self.assertFalse(KI.process_delivery_once(self.store,{}))
        with self.store.connection() as db:self.assertEqual(before,list(db.iterdump()))

    def test_manual_calls_are_blocked_before_creating_reservations(self):
        with self.store.connection() as db:before=list(db.iterdump())
        with patch.object(guard,'provider_lease',side_effect=lambda:self.lease(False)):
            with self.assertRaises(KI.ServiceError):KI.perform_manual_question(self.store,'AAA','q',False)
            with self.assertRaises(KI.ServiceError):KI.start_deep_analysis(self.store,'AAA')
        with self.store.connection() as db:self.assertEqual(before,list(db.iterdump()))

    def test_unrelated_permission_error_in_provider_is_not_swallowed(self):
        @guard.guard_operation(defer=True)
        def broken():raise PermissionError('not the lock')
        with self.assertRaises(PermissionError):broken()

    def test_broken_installed_lease_fails_closed_before_claim(self):
        @contextmanager
        def broken():raise guard.MaintenanceUnavailable();yield
        with patch.object(guard,'provider_lease',side_effect=broken):
            with self.assertRaises(guard.MaintenanceBusy):KI.process_analysis_once(self.store,{})

    def test_all_api_entrypoints_are_guarded_with_preserved_signatures(self):
        for name in ('service_http','perform_manual_question','resume_manual_research','collect_manual_research',
                     'submit_event_research','analyze_event','start_deep_analysis',
                     'process_analysis_once','process_delivery_once'):
            self.assertTrue(hasattr(getattr(KI,name),'__wrapped__'),name)

    @unittest.skipUnless(os.name=='posix','Linux flock integration')
    def test_real_shared_lease_blocks_exclusive_restart_and_reverse(self):
        lock=self.folder/'provider.lock'
        os.close(guardian.init_provider_lock(lock))
        with guard.provider_lease(lock) as shared:
            self.assertTrue(shared)
            with guardian.exclusive_provider_lease(lock) as exclusive:self.assertFalse(exclusive)
        with guardian.exclusive_provider_lease(lock) as exclusive:
            self.assertTrue(exclusive)
            with guard.provider_lease(lock) as shared:self.assertFalse(shared)
        with guard.provider_lease(lock) as shared:self.assertTrue(shared)

    @unittest.skipUnless(os.name=='posix','Linux process lease integration')
    def test_provider_process_crash_releases_lease_without_network_or_database_write(self):
        lock=self.folder/'provider.lock'
        os.close(guardian.init_provider_lock(lock))
        code="from ki2_ops_guard import provider_lease;import sys;\nwith provider_lease(sys.argv[1]) as acquired:\n print(acquired,flush=True);input()"
        child=subprocess.Popen([sys.executable,'-B','-c',code,str(lock)],
                               stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        try:
            self.assertEqual(child.stdout.readline().strip(),'True')
            with guardian.exclusive_provider_lease(lock) as acquired:self.assertFalse(acquired)
            child.terminate();child.communicate(timeout=5)
            with guardian.exclusive_provider_lease(lock) as acquired:self.assertTrue(acquired)
        finally:
            if child.poll() is None:child.kill()
            child.communicate(timeout=5)


if __name__=='__main__':unittest.main()
