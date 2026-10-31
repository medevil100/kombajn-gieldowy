"""Root installer for the reviewed KI 2 supervision bundle; no paid tests/messages.

Validates source checksums and expected existing KI before changes. Does not
modify the database, settings or backup unit. Requires KI running and no backup
or paid job in progress. Keeps code backups and rolls back failed installations.
"""
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import pwd
import shutil
import signal
import subprocess
import time
import urllib.request
import uuid

ROOT=Path('/home/ubuntu/ki2')
LIB=Path('/usr/local/lib/ki2-guardian')
UNITS=Path('/etc/systemd/system')
APP_FILES=('KI.py','ki2_ops_guard.py','ki2_guardian.py','test_guardian_20261031.py','AUTONOMIA_TECHNICZNA_20261031.md')


def command(*args):
    return subprocess.run(list(args),capture_output=True,text=True,timeout=180,check=True).stdout.strip()


def unit_active(name):
    return subprocess.run(['/usr/bin/systemctl','is-active','--quiet',name],check=False).returncode==0


def child_facts(script):
    properties=('Type=oneshot','TimeoutStartSec=20','User=ubuntu','Group=ubuntu',
                'UMask=0077','NoNewPrivileges=yes','PrivateTmp=yes','ProtectSystem=strict',
                'ProtectHome=read-only','ReadWritePaths=/home/ubuntu/ki2',
                'ProtectKernelTunables=yes','ProtectKernelModules=yes','ProtectControlGroups=yes',
                'RestrictSUIDSGID=yes','LockPersonality=yes','RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6')
    args=['/usr/bin/systemd-run','--unit=ki2-guardian-preflight-'+uuid.uuid4().hex,
          '--collect','--wait','--pipe']
    args+=['--property='+prop for prop in properties]
    args+=['/usr/bin/python3','-I',str(script),'--internal-facts','--db',str(ROOT/'KI.matrix.sqlite3')]
    return json.loads(command(*args))


@contextmanager
def exclusive_lock():
    import fcntl
    path=Path('/run/ki2-guardian/provider.lock')
    path.parent.mkdir(parents=True,exist_ok=True,mode=0o755)
    fd=os.open(path,os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o644)
    os.fchmod(fd,0o644)
    try:
        fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        yield
    finally:os.close(fd)


def install():
    if os.geteuid()!=0:raise RuntimeError('Uruchom instalator przez sudo.')
    source=Path(__file__).resolve().parent
    manifest=json.loads((source/'MANIFEST_GUARDIAN_20261031.json').read_text(encoding='utf-8'))
    for name,digest in manifest['sha256'].items():
        if '/' in name or '\\' in name:raise RuntimeError('Niepoprawny manifest.')
        if hashlib.sha256((source/name).read_bytes()).hexdigest()!=digest:
            raise RuntimeError('Niezgodna suma pliku: '+name)
    before=(ROOT/'KI.py').read_bytes().replace(b'\r\n',b'\n')
    if hashlib.sha256(before).hexdigest()!=manifest['previous_ki_normalized_sha256']:
        raise RuntimeError('Inna wersja KI na VPS. Niczego nie zmieniono.')
    if not unit_active('ki2.service'):raise RuntimeError('KI nie działa; najpierw sprawdź jego stan.')
    backup_state=command('/usr/bin/systemctl','show','ki2-backup.service','--property=ActiveState','--value')
    if backup_state not in ('inactive','failed'):raise RuntimeError('Backup w toku; zaczekaj na zakończenie.')
    # This read-only preflight is run as ubuntu so SQLite sidecars keep their owner.
    if child_facts(source/'ki2_guardian.py')['busy_jobs']:
        raise RuntimeError('Trwa analiza lub wysyłka. Zaczekaj; niczego nie zmieniono.')
    if unit_active('ki2-guardian.timer') or unit_active('ki2-guardian.service'):
        raise RuntimeError('Nadzór już działa. Nie uruchomiono drugiej instalacji.')
    backup=ROOT/('backup-guardian-code-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    backup.mkdir(mode=0o700)
    LIB.mkdir(parents=True,exist_ok=True,mode=0o755)
    owner=pwd.getpwnam('ubuntu')
    mappings=[(name,ROOT/name,True) for name in APP_FILES]
    mappings += [('ki2_guardian.py',LIB/'ki2_guardian.py',False),
                 ('ki2-guardian.service',UNITS/'ki2-guardian.service',False),
                 ('ki2-guardian.timer',UNITS/'ki2-guardian.timer',False),
                 ('ki2-backup-guardian.conf',UNITS/'ki2-backup.service.d'/'50-guardian-ordering.conf',False)]
    saved=[]
    with exclusive_lock():
        # Once the app is patched this exclusive lease also protects rollback.
        try:
            command('/usr/bin/systemctl','stop','ki2.service')
            for index,(name,target,is_app) in enumerate(mappings):
                target.parent.mkdir(parents=True,exist_ok=True,mode=0o755)
                existed=target.exists()
                metadata=target.stat() if existed else None
                old=backup/str(index)
                if existed:shutil.copy2(target,old)
                saved.append((target,old,metadata))
                shutil.copy2(source/name,target)
                os.chmod(target,0o644)
                os.chown(target,owner.pw_uid if is_app else 0,owner.pw_gid if is_app else 0)
            command('/usr/bin/systemctl','daemon-reload')
            command('/usr/bin/systemd-analyze','verify',str(UNITS/'ki2-guardian.service'),str(UNITS/'ki2-guardian.timer'),str(UNITS/'ki2-backup.service'))
            command('/usr/bin/systemctl','start','ki2.service')
            healthy=False
            proxyfree=urllib.request.build_opener(urllib.request.ProxyHandler({}))
            for _ in range(30):
                try:
                    with proxyfree.open('http://127.0.0.1:8501/_stcore/health',timeout=2) as response:
                        healthy=response.status==200 and response.read(64).strip()==b'ok'
                except OSError:pass
                if healthy:break
                time.sleep(2)
            if not healthy:raise RuntimeError('Panel nie wystartował; przywracanie poprzedniego kodu.')
            child_facts(LIB/'ki2_guardian.py')
            # --check performs no state writes, restarts, or Telegram requests.
            report=json.loads(command('/usr/bin/python3','-I',str(LIB/'ki2_guardian.py')))
            if report['status'] not in ('HEALTHY','GRACE'):
                raise RuntimeError('Nadzór zgłasza problem; instalacja wycofana.')
        except BaseException:
            subprocess.run(['/usr/bin/systemctl','stop','ki2.service'],check=False)
            for target,old,metadata in reversed(saved):
                if metadata is None:target.unlink(missing_ok=True)
                else:
                    shutil.copy2(old,target)
                    os.chown(target,metadata.st_uid,metadata.st_gid)
            subprocess.run(['/usr/bin/systemctl','daemon-reload'],check=False)
            subprocess.run(['/usr/bin/systemctl','start','ki2.service'],check=False)
            raise
    command('/usr/bin/systemctl','enable','--now','ki2-guardian.timer')
    command('/usr/bin/systemctl','start','ki2-guardian.service')
    print('Nadzór techniczny zainstalowany. Kopia kodu:',backup,flush=True)
    print('Baza, ustawienia, kolejki i godzina kopii zachowane. Dodano kolejność backupu po aktywnym nadzorze.',flush=True)
    print('Kontrole co 2 minuty; bez testowych wiadomości i zapytań AI.',flush=True)


if __name__=='__main__':
    def interrupted(signum,frame):
        raise SystemExit(128+signum)
    signal.signal(signal.SIGTERM,interrupted)
    signal.signal(signal.SIGHUP,interrupted)
    install()
