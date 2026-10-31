"""Verify the new reader in the actual systemd sandbox before replacing monitor.

No KI restart, no DB/settings writes, no notification or paid test. Security
properties stay unchanged. Preserve incident/restart state for natural recovery.
"""
import hashlib
import json
import os
from pathlib import Path
import pwd
import shutil
import subprocess
from datetime import datetime, timezone


def call(*args):
    return subprocess.run(list(args),capture_output=True,text=True,timeout=120,check=True)


def apply():
    if os.geteuid()!=0:raise SystemExit('Uruchom przez sudo.')
    source=Path(__file__).resolve().parent
    metadata=json.loads((source/'OWNER_FIX_METADATA.json').read_text(encoding='utf-8'))
    new=source/'ki2_guardian.py'
    installed=Path('/usr/local/lib/ki2-guardian/ki2_guardian.py')
    if hashlib.sha256(new.read_bytes()).hexdigest()!=metadata['new_monitor_sha256']:
        raise SystemExit('Niezgodny plik poprawki.')
    old_hash=hashlib.sha256(installed.read_bytes()).hexdigest()
    if old_hash not in (metadata['previous_monitor_sha256'],metadata['new_monitor_sha256']):
        raise SystemExit('Inna wersja nadzoru. Przerwano bez zmiany kodu.')
    call('/usr/bin/systemctl','stop','ki2-guardian.timer')
    if subprocess.run(['/usr/bin/systemctl','is-active','--quiet','ki2-guardian.service'],check=False).returncode==0:
        raise SystemExit('Kontrola jeszcze trwa. Zaczekaj i uruchom poprawkę ponownie.')
    properties=[
        'Type=oneshot','TimeoutStartSec=90','User=root','Group=root','UMask=0077',
        'StateDirectory=ki2-guardian','StateDirectoryMode=0700',
        'RuntimeDirectory=ki2-guardian','RuntimeDirectoryMode=0755','RuntimeDirectoryPreserve=yes',
        'Nice=10','NoNewPrivileges=yes','PrivateTmp=yes','ProtectSystem=strict',
        'ProtectHome=read-only','ReadWritePaths=/home/ubuntu/ki2',
        'ProtectKernelTunables=yes','ProtectKernelModules=yes','ProtectControlGroups=yes',
        'RestrictSUIDSGID=yes','LockPersonality=yes','RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6',
    ]
    unit='ki2-guardian-owner-check-'+datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')
    args=['/usr/bin/systemd-run','--unit='+unit,'--collect','--wait','--pipe']
    for prop in properties:args.append('--property='+prop)
    args+=['/usr/bin/python3','-I',str(new)]  # check only: no state/notifications/actions
    print('Sprawdzanie nowego odczytu w pełnym środowisku usługi…',flush=True)
    completed=call(*args)
    report=None
    for line in completed.stdout.splitlines():
        try:value=json.loads(line)
        except ValueError:continue
        if isinstance(value,dict) and 'status' in value:report=value
    if not report or report.get('status')!='HEALTHY':
        print(json.dumps(report or {'status':'NO_REPORT'},ensure_ascii=False),flush=True)
        raise SystemExit('Przerwano. Kod bez zmian; timer nadzoru pozostaje zatrzymany.')
    print('Kontrola w ograniczeniach systemd: HEALTHY. Bez akcji i wysyłki.',flush=True)
    root=Path('/home/ubuntu/ki2')
    backup=root/('backup-guardian-owner-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    backup.mkdir(mode=0o700)
    shutil.copy2(installed,backup/'ki2_guardian.root.py')
    app=root/'ki2_guardian.py'
    if app.exists():shutil.copy2(app,backup/'ki2_guardian.app.py')
    temp=installed.with_name(installed.name+'.new')
    shutil.copy2(new,temp);os.chmod(temp,0o644);os.chown(temp,0,0)
    os.replace(temp,installed)
    owner=pwd.getpwnam('ubuntu')
    temp=app.with_name(app.name+'.new')
    shutil.copy2(new,temp);os.chmod(temp,0o644);os.chown(temp,owner.pw_uid,owner.pw_gid)
    os.replace(temp,app)
    for name in ('test_guardian_20261031.py','install_guardian_20261031.py','AUTONOMIA_TECHNICZNA_20261031.md'):
        target=root/name
        if target.exists():shutil.copy2(target,backup/name)
        shutil.copy2(source/name,target);os.chmod(target,0o644);os.chown(target,owner.pw_uid,owner.pw_gid)
    # Keep durable state and all existing unit security settings.
    call('/usr/bin/systemctl','start','ki2-guardian.service')
    state=json.loads(Path('/var/lib/ki2-guardian/state.json').read_text(encoding='utf-8'))
    if state.get('last_status')!='HEALTHY':
        print('Kontrola rzeczywistej usługi:',state.get('last_status'),flush=True)
        raise SystemExit('Timer pozostaje zatrzymany. Prześlij log nadzoru; KI nie było restartowane.')
    call('/usr/bin/systemctl','start','ki2-guardian.timer')
    print('Poprawka odczytu wdrożona. Kopia:',backup,flush=True)
    print('KI nie było restartowane. Stan incydentu zachowany; powrót zgłosi zwykły cykl nadzoru.',flush=True)


if __name__=='__main__':apply()
