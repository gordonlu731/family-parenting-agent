"""Private backup/monitor timers in the current user's manager. Never restart the app."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

sys.path.insert(0,str(Path(__file__).resolve().parent))
import user_service as service
import operations

PREFIX='family-parenting-agent-'


def units(root,data,backups):
    result={}
    for action in ('backup','check'):
        name=PREFIX+action
        result[name+'.service']=f'''[Unit]
Description=Private family {action}
[Service]
Type=oneshot
ExecStart={service.quote(root/'.venv/bin/python')} -I -B {service.quote(root/'scripts/user_operations.py')} {action} --root {service.quote(root)} --data-dir {service.quote(data)} --backup-dir {service.quote(backups)}
UMask=0077
NoNewPrivileges=yes
MemoryMax=128M
CPUQuota=25%
TasksMax=16
TimeoutStartSec=120
'''
        schedule='OnCalendar=*-*-* 03:15:00 Asia/Shanghai\nPersistent=true\nRandomizedDelaySec=300' if action=='backup' else 'OnBootSec=15min\nOnUnitActiveSec=1h'
        result[name+'.timer']=f'''[Unit]
Description=Private family {action} schedule
[Timer]
{schedule}
Unit={name}.service
[Install]
WantedBy=timers.target
'''
    return result


def install(root,data,backups):
    # Check a real backup and isolated restore before activating any schedule.
    snapshot=operations.backup(data/'family.sqlite3',backups,keep=14)
    operations.restore_check(backups/snapshot['backup'])
    if operations.check(data/'family.sqlite3',backups)['status']!='ok':
        raise ValueError('preflight_monitor_failed')
    folder=Path.home()/'.config/systemd/user'
    folder.mkdir(parents=True,exist_ok=True,mode=0o700)
    service.owned(folder,directory=True)
    for name,body in units(root,data,backups).items():
        target=folder/name
        if target.exists() or target.is_symlink():
            service.owned(target)
            previous=target.read_bytes()
            if previous!=body.encode():
                saved=folder/(name+'.previous-'+hashlib.sha256(previous).hexdigest())
                if not saved.exists():
                    with saved.open('xb') as stream:stream.write(previous)
                    saved.chmod(0o600)
        tmp=folder/(name+'.new')
        fd=os.open(tmp,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        with os.fdopen(fd,'w') as stream:stream.write(body)
        os.replace(tmp,target)
    def run(*args):subprocess.run(['systemctl','--user',*args],check=True,capture_output=True,timeout=120)
    run('daemon-reload')
    # Actual oneshots must succeed before either timer is enabled.
    run('start',PREFIX+'backup.service');run('start',PREFIX+'check.service')
    run('enable','--now',PREFIX+'backup.timer',PREFIX+'check.timer')
    return {'status':'ok','scope':'current-user','retention':14,'off_host':False}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=['install','backup','check'])
    p.add_argument('--root',type=Path,required=True)
    p.add_argument('--data-dir',type=Path,required=True)
    p.add_argument('--backup-dir',type=Path,required=True)
    a=p.parse_args()
    try:
        os.umask(0o077)
        root,data=service.paths(a.root,a.data_dir)
        service.environment(root,data)  # Validate config; no model/environment injection.
        service.require(not any(x.is_symlink() for x in (a.backup_dir,*a.backup_dir.parents)))
        backups=operations.private_directory(a.backup_dir)
        if a.action=='install':result=install(root,data,backups)
        elif a.action=='backup':result=operations.backup(data/'family.sqlite3',backups,keep=14)
        else:result=operations.check(data/'family.sqlite3',backups)
        print(json.dumps(result))
        return 0 if result['status']=='ok' else 1
    except Exception:
        print('{"status":"failed","code":"private_user_operations_failed"}')
        return 1


if __name__=='__main__':raise SystemExit(main())
