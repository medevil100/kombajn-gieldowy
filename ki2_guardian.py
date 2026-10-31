"""Independent KI 2 supervisor: RO audit, bounded cooperative recovery, incident alerts.

Standard library only. --check is read-only and sends nothing. Production mode
requires --apply and a root-installed unit. Never imports KI, replays jobs, calls
OpenAI/Tavily, purges data, or starts a manually stopped KI service.
"""
import argparse
from contextlib import closing, contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import time
import uuid
import urllib.error
import urllib.request

GIB = 1024**3
DB = Path('/home/ubuntu/ki2/KI.matrix.sqlite3')
LOCK = Path('/run/ki2-guardian/provider.lock')
STATE = Path('/var/lib/ki2-guardian/state.json')
PROPERTIES = 'ActiveState,SubState,Result,MainPID,ActiveEnterTimestampMonotonic'
RESTART_CODES = {'PANEL_DOWN', 'SCANNER_STALE', 'WORKER_ANALYSIS_STALE',
                 'WORKER_TELEGRAM_STALE', 'CYCLE_STUCK', 'CYCLE_MISSING'}


def stamp(value):
    try:
        result = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        return result.astimezone(timezone.utc) if result.tzinfo else None
    except (TypeError, ValueError, OverflowError):
        return None


def age(value, now):
    value = stamp(value)
    return (now-value).total_seconds() if value else None


def system_unit(name):
    result = subprocess.run(['/usr/bin/systemctl', 'show', name, '--property='+PROPERTIES],
                            capture_output=True, text=True, timeout=10, check=False)
    if result.returncode:
        raise RuntimeError('SYSTEMD_UNAVAILABLE')
    props = dict(line.split('=', 1) for line in result.stdout.splitlines() if '=' in line)
    if not props.get('ActiveState'):
        raise RuntimeError('SYSTEMD_UNAVAILABLE')
    return props


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def opener():
    return urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())


def panel_health():
    try:
        with opener().open('http://127.0.0.1:8501/_stcore/health', timeout=5) as response:
            return response.status == 200 and response.read(64).strip() == b'ok'
    except (OSError, urllib.error.URLError):
        return False


def is_root():
    return os.name=='posix' and os.geteuid()==0


class DatabaseAuditUnavailable(RuntimeError):
    """Bounded diagnosis; never propagate subprocess stderr or credentials."""
    def __init__(self, reason, child_error_type=None):
        super().__init__('DATABASE_AUDIT_UNAVAILABLE')
        self.diagnostic={'reason':reason}
        if isinstance(child_error_type,str) and re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,63}',child_error_type):
            self.diagnostic['child_error_type']=child_error_type


def database_facts(path):
    # SQLite WAL/SHM must retain the application's owner, even if the supervisor
    # is root. The child executes this trusted isolated script, not user code.
    if is_root():
        properties=(
            'Type=oneshot','TimeoutStartSec=20','User=ubuntu','Group=ubuntu','UMask=0077',
            'NoNewPrivileges=yes','PrivateTmp=yes','ProtectSystem=strict',
            'ProtectHome=read-only','ReadWritePaths=/home/ubuntu/ki2',
            'ProtectKernelTunables=yes','ProtectKernelModules=yes','ProtectControlGroups=yes',
            'RestrictSUIDSGID=yes','LockPersonality=yes',
            'RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6',
        )
        command=['/usr/bin/systemd-run','--unit=ki2-guardian-reader-'+uuid.uuid4().hex,
                 '--collect','--wait','--pipe']
        command+=['--property='+prop for prop in properties]
        command+=['/usr/bin/python3','-I',str(Path(__file__).resolve()),
                  '--internal-facts','--db',str(path)]
        try:
            child=subprocess.run(command,capture_output=True,text=True,encoding='utf-8',
                                 timeout=35,check=False)
        except (OSError,subprocess.TimeoutExpired) as exc:
            raise DatabaseAuditUnavailable('CHILD_START_FAILED',type(exc).__name__) from None
        if len(child.stdout)>65536:
            raise DatabaseAuditUnavailable('OUTPUT_LIMIT')
        try: data=json.loads(child.stdout)
        except (ValueError,TypeError):
            raise DatabaseAuditUnavailable('INVALID_CHILD_RESPONSE') from None
        if child.returncode:
            raise DatabaseAuditUnavailable('CHILD_FAILED',data.get('error_type') if isinstance(data,dict) else None)
        if not isinstance(data,dict) or type(data.get('busy_jobs')) is not int or data['busy_jobs']<0:
            raise DatabaseAuditUnavailable('INVALID_CHILD_SCHEMA')
        return data
    return _database_facts_local(path)


def _database_facts_local(path):
    """Only small status records/aggregates; do not load observation/research payloads."""
    with closing(sqlite3.connect(path.as_uri()+'?mode=ro', uri=True, timeout=2)) as db:
        db.execute('PRAGMA query_only=ON')
        runtime = {}
        for key, updated, payload in db.execute("SELECT key,updated_at,payload FROM runtime WHERE key IN ('scanner','worker_analysis','worker_telegram')"):
            data=json.loads(payload)
            runtime[key] = {'updated_at': updated, **{k:data[k] for k in
                ('pid','status','cycles_this_run','skipped_slots','last_cycle_status','next_cycle_UTC') if k in data}}
        cfg = db.execute("SELECT payload FROM legacy_state WHERE section='settings'").fetchone()
        settings = json.loads(cfg[0]) if cfg else {}
        cycle = db.execute('SELECT started_at,finished_at,status FROM cycles ORDER BY rowid DESC LIMIT 1').fetchone()
        recent=[r[0] for r in db.execute('SELECT status FROM cycles WHERE finished_at IS NOT NULL ORDER BY rowid DESC LIMIT 3')]
        busy = db.execute("SELECT COUNT(*) FROM analysis_jobs WHERE state IN ('BUSY_CONTEXT','BUSY_AI')").fetchone()[0]
        busy += db.execute("SELECT COUNT(*) FROM outbox WHERE status='SENDING'").fetchone()[0]
        busy += db.execute("SELECT COUNT(*) FROM gpt_chat_turns WHERE state='REQUESTED'").fetchone()[0]
        busy += db.execute("SELECT COUNT(*) FROM deep_reports WHERE state IN ('QUEUED','RUNNING')").fetchone()[0]
        return {'runtime': runtime, 'cadence': settings.get('auto_scan_interval', 15),
                'cycle': dict(zip(('started_at','finished_at','status'),cycle)) if cycle else None,
                'busy_jobs': busy,'recent_cycle_statuses':recent}


def collect(db=DB, now=None):
    now = now or datetime.now(timezone.utc)
    result = {'at': now.isoformat(), 'issues': [], 'facts': {}}
    facts = result['facts']
    for key, name in (('service','ki2.service'),('backup','ki2-backup.service'),('timer','ki2-backup.timer')):
        facts[key] = system_unit(name)
    facts['uptime'] = max(0., time.monotonic()-int(facts['service'].get('ActiveEnterTimestampMonotonic') or 0)/1e6)
    facts['disk_free'] = shutil.disk_usage(db.parent).free
    facts['db_bytes'] = db.stat().st_size
    files = [p for p in (db.parent/'backups').glob('ki2-*.sqlite3')
             if re.fullmatch(r'ki2-\d{8}T\d{12}Z\.sqlite3',p.name) and p.is_file() and not p.is_symlink()]
    latest = max(files,key=lambda p:p.stat().st_mtime,default=None)
    facts['backup_age'] = now.timestamp()-latest.stat().st_mtime if latest else None
    facts['backup_name'] = latest.name if latest else None
    # A managed backup intentionally stops the panel/scanner. Do not compete with it.
    if (facts['backup']['ActiveState'] not in ('active','activating','deactivating')
            and facts['service']['ActiveState']=='active' and facts['uptime']>=300):
        facts.update(database_facts(db))
        facts['panel_ok'] = panel_health()
    return assess(result, now)


def assess(result, now):
    f=result['facts'];issues=result['issues']
    def add(code,message): issues.append({'code':code,'message':message})
    if f['backup']['ActiveState'] in ('active','activating','deactivating'):
        result['status']='MAINTENANCE'
        return result
    active=f['service']['ActiveState']
    if active in ('activating','deactivating') or active=='active' and f['uptime']<300:
        result['status']='GRACE'
        return result
    if active=='inactive' and f['service'].get('Result','success')=='success':
        result['status']='PAUSED'
        return result
    if active!='active': add('SERVICE_FAILED','Usługa KI wymaga interwencji; nie uruchomiono jej samoczynnie.')
    if f['disk_free'] < f['db_bytes']+2*GIB:
        add('DISK_CRITICAL','Za mało wolnego miejsca na następną bezpieczną kopię bazy.')
    elif f['disk_free'] < max(5*GIB,2*f['db_bytes']+3*GIB):
        add('DISK_LOW','Mały zapas wolnego miejsca na dysku.')
    if f['backup'].get('Result','success')!='success': add('BACKUP_FAILED','Ostatnie zadanie kopii zakończyło się błędem.')
    if f['timer']['ActiveState']!='active': add('BACKUP_TIMER_OFF','Timer kopii jest nieaktywny.')
    if f['backup_age'] is None or not 0<=f['backup_age']<=30*3600:
        add('BACKUP_STALE','Brak kopii z ostatnich 30 godzin albo nieprawidłowy czas kopii.')
    if active=='active':
        if not f.get('panel_ok'): add('PANEL_DOWN','Panel KI nie odpowiada poprawnie na kontrolę lokalną.')
        runtime=f.get('runtime',{});scanner=runtime.get('scanner',{})
        scanner_age=age(scanner.get('updated_at'),now)
        if scanner_age is not None and scanner_age < -30:
            add('CLOCK_INVALID','Heartbeat skanera ma czas z przyszłości; wymagana kontrola zegara.')
        elif (scanner_age is None or scanner_age>180 or scanner.get('status') not in ('RUNNING','PAUSED')
              or type(scanner.get('pid')) is not int or scanner['pid']<=0):
            add('SCANNER_STALE','Brak aktualnego heartbeat skanera.')
        for kind in ('analysis','telegram'):
            worker=runtime.get('worker_'+kind,{})
            worker_age=age(worker.get('updated_at'),now)
            if worker_age is not None and worker_age < -30:
                add('CLOCK_INVALID','Heartbeat modułu ma czas z przyszłości; wymagana kontrola zegara.')
            elif (worker_age is None or worker_age>300 or worker.get('pid')!=scanner.get('pid')
                    or worker.get('status') not in ('READY','DISABLED')):
                add('WORKER_'+kind.upper()+'_STALE','Brak aktualnego potwierdzenia modułu '+kind+'.')
        if f.get('cadence')!=0:
            recent=f.get('recent_cycle_statuses',[])
            if len(recent)==3 and all(s in ('ERROR','RATE_LIMITED','CAPACITY_LIMITED','INCOMPLETE_CANDLE_STATUS') for s in recent):
                add('DATA_SOURCE_PROBLEM','Trzy ostatnie cykle zakończyły się błędem pobrania lub limitem dostawcy. Wymagana kontrola; bez restartowania w pętli.')
            cycle=f.get('cycle')
            if cycle and cycle['status']=='RUNNING':
                elapsed=age(cycle['started_at'],now)
                if elapsed is not None and elapsed>2700: add('CYCLE_STUCK','Cykl skanera trwa ponad 45 minut.')
            else:
                elapsed=age((cycle or {}).get('finished_at'),now)
                if elapsed is None or elapsed>3600: add('CYCLE_MISSING','Brak zakończonego cyklu od ponad godziny.')
    result['status']='DEGRADED' if issues else 'HEALTHY'
    return result


def transition(previous, report, now):
    """Persistent hysteresis, 30-minute cooldown, max two attempts per rolling day."""
    state=json.loads(json.dumps(previous));codes={i['code'] for i in report['issues']}
    state['failures']={code:state.get('failures',{}).get(code,0)+1 for code in codes}
    state['healthy_runs']=state.get('healthy_runs',0)+1 if report['status']=='HEALTHY' else 0
    confirmed={code for code,n in state['failures'].items() if n>=3}
    notification=None
    if confirmed and not state.get('incident'):
        state['incident']=True
        notification='AWARIA KI 2\n'+'\n'.join(i['message'] for i in report['issues'] if i['code'] in confirmed)
    elif state['healthy_runs']>=2 and state.get('incident'):
        state['incident']=False
        notification='KI 2: przywrócono prawidłowe działanie nadzorowanych modułów, kopii i dysku.'
    attempts=[t for t in state.get('restarts',[]) if now-t<86400]
    state['restarts']=attempts
    action='NONE'
    if confirmed & RESTART_CODES and report['facts']['service']['ActiveState']=='active':
        if report['facts'].get('busy_jobs',1): action='BLOCKED_INFLIGHT'
        elif len(attempts)>=2 or attempts and now-attempts[-1]<1800: action='BLOCKED_LIMIT'
        else: action='RESTART_ELIGIBLE'
    if 'CLOCK_INVALID' in codes or 'DISK_CRITICAL' in codes:
        action='BLOCKED_INTERVENTION'
    state['last_check']=report['at'];state['last_status']=report['status'];state['last_action']=action
    return state,action,notification


def save_state(path,state):
    temp=path.with_name(path.name+'.new')
    fd=os.open(temp,os.O_CREAT|os.O_TRUNC|os.O_WRONLY,0o600)
    with os.fdopen(fd,'w',encoding='utf-8') as handle:
        json.dump(state,handle,ensure_ascii=False,separators=(',',':'));handle.flush();os.fsync(handle.fileno())
    os.replace(temp,path)


def init_provider_lock(path=LOCK):
    path.parent.mkdir(parents=True,exist_ok=True,mode=0o755)
    fd=os.open(path,os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o644)
    os.fchmod(fd,0o644)
    return fd


@contextmanager
def exclusive_provider_lease(path=LOCK):
    import fcntl
    fd=init_provider_lock(path)
    try:
        try: fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            yield False
            return
        yield True
    finally:
        os.close(fd)


def notify_telegram(message,secrets_path):
    """One durable attempt per transition; no retries after unknown delivery."""
    import tomllib
    try:
        keys=tomllib.loads(secrets_path.read_text(encoding='utf-8-sig'))
        token=str(keys.get('TELEGRAM_BOT_TOKEN') or '').strip()
        chat=str(keys.get('TELEGRAM_CHAT_ID') or '').strip()
        if not re.fullmatch(r'\d+:[A-Za-z0-9_-]+',token) or not re.fullmatch(r'-?\d+',chat):
            return 'KEYS_UNAVAILABLE'
        request=urllib.request.Request('https://api.telegram.org/bot'+token+'/sendMessage',
            data=json.dumps({'chat_id':chat,'text':message[:3500],'disable_web_page_preview':True}).encode(),
            headers={'Content-Type':'application/json'},method='POST')
        with opener().open(request,timeout=15) as response:
            body=json.loads(response.read(16384))
        receipt=body.get('result') or {}
        if body.get('ok') is True and type(receipt.get('message_id')) is int and str(receipt.get('chat',{}).get('id'))==chat:
            return 'SENT'
        return 'UNCERTAIN'
    except Exception:
        # Never log an exception containing the bot URL, credentials, or response.
        return 'UNCERTAIN'


def run(db=DB,state_path=STATE,apply=False,notify=False,restart=False,now=None):
    now=now or datetime.now(timezone.utc)
    try:
        report=collect(db,now)
    except Exception as exc:
        report={'at':now.isoformat(),'status':'DEGRADED','error_type':type(exc).__name__,
                'issues':[{'code':'AUDIT_UNAVAILABLE','message':'Nadzór KI nie może potwierdzić stanu systemu; wymagana kontrola.'}],
                'facts':{'service':{'ActiveState':'unknown'}}}
        if isinstance(exc,DatabaseAuditUnavailable):
            report['diagnostic']=exc.diagnostic
    if not apply:
        return report
    previous=json.loads(state_path.read_text(encoding='utf-8')) if state_path.exists() else {}
    state,action,message=transition(previous,report,now.timestamp())
    if message and notify:
        state['notification']='ATTEMPT_RESERVED'
    save_state(state_path,state)
    report['action']=action
    if message and notify:
        state['notification']=notify_telegram(message,db.parent/'.streamlit'/'secrets.toml')
        report['notification']=state['notification']
        save_state(state_path,state)
    if restart and action=='RESTART_ELIGIBLE':
        with exclusive_provider_lease() as acquired:
            if not acquired: report['action']='BLOCKED_PROVIDER_LEASE'
            # Recheck after closing the gate. No cooperative operation can start.
            elif system_unit('ki2-backup.service')['ActiveState'] in ('active','activating','deactivating'):
                report['action']='BLOCKED_BACKUP'
            elif database_facts(db)['busy_jobs']:
                report['action']='BLOCKED_INFLIGHT'
            else:
                state['restarts'].append(now.timestamp())
                state['last_action']='RESTART_REQUESTED'
                save_state(state_path,state)  # crash cannot reset the restart budget
                completed=subprocess.run(['/usr/bin/systemctl','try-restart','ki2.service'],
                                         capture_output=True,timeout=90,check=False)
                report['action']='RESTART_REQUESTED' if completed.returncode==0 else 'RESTART_FAILED'
    state['last_action']=report.get('action','NONE')
    save_state(state_path,state)
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db',type=Path,default=DB)
    parser.add_argument('--state',type=Path,default=STATE)
    parser.add_argument('--apply',action='store_true')
    parser.add_argument('--notify',action='store_true')
    parser.add_argument('--auto-restart',action='store_true')
    parser.add_argument('--init-lock',action='store_true')
    parser.add_argument('--internal-facts',action='store_true',help=argparse.SUPPRESS)
    args=parser.parse_args()
    try:
        if args.internal_facts:
            print(json.dumps(_database_facts_local(args.db.resolve()),ensure_ascii=False),flush=True)
        elif args.init_lock:
            os.close(init_provider_lock())
        elif args.apply:
            import fcntl
            os.close(init_provider_lock())
            args.state.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
            with (args.state.parent/'run.lock').open('a+b') as handle:
                fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
                print(json.dumps(run(args.db.resolve(),args.state,True,args.notify,args.auto_restart),ensure_ascii=False),flush=True)
        else:
            print(json.dumps(run(args.db.resolve()),ensure_ascii=False),flush=True)
    except Exception as exc:
        print(json.dumps({'status':'CHECK_FAILED','error_type':type(exc).__name__}),flush=True)
        raise SystemExit(1)
