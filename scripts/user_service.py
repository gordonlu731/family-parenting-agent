"""Private loopback deployment in the current non-root user's systemd manager.

Equivalent fallback when rootless containers are unavailable. No sudo, system
unit, host Docker socket, model call, database replacement, or volume removal.
"""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys

sys.path.insert(0,str(Path(__file__).resolve().parent))
from deploy import read_env, https_url

UNIT='family-parenting-agent.service'


def require(ok):
    if not ok:raise ValueError('user_deployment_contract_refused')


def owned(path, *, directory=False):
    path=Path(path)
    require(not any(p.is_symlink() for p in (path,*path.parents)))
    info=path.stat();require(info.st_uid==os.geteuid() and not info.st_mode&0o077)
    require(path.is_dir() if directory else path.is_file())
    return path


def paths(root,data):
    require(not any(p.is_symlink() for p in (Path(data),*Path(data).parents)))
    root,data=Path(root).resolve(),Path(data).resolve()
    require(os.geteuid()!=0 and sys.version_info>=(3,12))
    require(root.is_dir() and (root/'backend/app.py').is_file() and (root/'dist/index.html').is_file())
    require((root/'.venv/bin/python').is_file())
    require(data!=root and not data.is_relative_to(root))
    return root,data


def environment(root,data):
    owned(root/'.env');owned(data,directory=True)
    values=read_env(root/'.env')
    require(values.get('DEMO_MODE')=='false' and values.get('APP_PORT')=='18080')
    # The listener stays on loopback in both modes. HTTPS belongs to the
    # separately configured reverse proxy; never downgrade its session cookie.
    origin=values.get('PUBLIC_ORIGIN','')
    private=origin=='http://127.0.0.1:18080' and values.get('COOKIE_SECURE')=='false'
    if not private:
        require(values.get('COOKIE_SECURE')=='true')
        origin=https_url(origin, origin=True)
    require(len(values.get('BOOTSTRAP_TOKEN',''))>=32)
    allowed={'BOOTSTRAP_TOKEN','PUBLIC_ORIGIN','COOKIE_SECURE','DEMO_MODE','MODEL_API_KEY','MODEL_BASE_URL','MODEL_ID',
             'MODEL_ENABLE_THINKING','MODEL_DAILY_REQUEST_LIMIT','PANTRY_RECONFIRM_DAYS'}
    env={k:values[k] for k in allowed if k in values}
    env['PUBLIC_ORIGIN']=origin
    env.update(PATH=os.environ.get('PATH','/usr/bin:/bin'),HOME=str(Path.home()),LANG='C.UTF-8',
               APP_DB=str(data/'family.sqlite3'),PYTHONDONTWRITEBYTECODE='1')
    return env


def quote(value):
    value=str(value);require(not any(c in value for c in '\r\n\x00'))
    return '"'+value.replace('\\','\\\\').replace('"','\\"').replace('%','%%')+'"'


def unit(root,data):
    # run changes cwd itself. WorkingDirectory does not use ExecStart's quoting.
    return f'''[Unit]
Description=Private family application (current user only)
[Service]
ExecStart={quote(root/'.venv/bin/python')} -I -B {quote(root/'scripts/user_service.py')} run --root {quote(root)} --data-dir {quote(data)}
Restart=on-failure
RestartSec=5
NoNewPrivileges=yes
UMask=0077
MemoryMax=512M
CPUQuota=75%
TasksMax=128
StandardOutput=journal
StandardError=journal
[Install]
WantedBy=default.target
'''


def install(root,data, *, invoke=subprocess.run, home=None):
    root,data=paths(root,data)
    if not data.exists():data.mkdir(parents=True,mode=0o700)
    environment(root,data)
    home=Path.home() if home is None else Path(home)
    folder=home/'.config/systemd/user';folder.mkdir(parents=True,exist_ok=True,mode=0o700)
    target=folder/UNIT;body=unit(root,data).encode()
    # Updating a user-owned unit is ordinary deployment. Retain its prior version.
    require(not target.is_symlink())
    if target.exists() and target.read_bytes()!=body:
        require(target.stat().st_uid==os.geteuid())
        import hashlib
        backup=folder/(UNIT+'.previous-'+hashlib.sha256(target.read_bytes()).hexdigest())
        if not backup.exists():backup.write_bytes(target.read_bytes());backup.chmod(0o600)
    tmp=folder/(UNIT+'.new')
    fd=os.open(tmp,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'wb') as stream:stream.write(body)
    os.replace(tmp,target)
    for args in (['daemon-reload'],['enable',UNIT],['restart',UNIT]):
        invoke(['systemctl','--user',*args],check=True,capture_output=True,timeout=30)
    return {'unit':UNIT,'scope':'current-user','private_loopback_only':True,'database_retained':True}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['check','install','run'])
    p.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1]);p.add_argument('--data-dir',type=Path,required=True)
    args=p.parse_args()
    try:
        root,data=paths(args.root,args.data_dir)
        if args.action=='install':result=install(root,data)
        else:
            env=environment(root,data)
            if args.action=='run':
                os.chdir(root);os.execve(root/'.venv/bin/python',[str(root/'.venv/bin/python'),'-B','-m','uvicorn',
                    'backend.app:app','--host','127.0.0.1','--port','18080','--workers','1','--no-access-log'],env)
            result={'non_root':True,'private_config_checked':True,'model_called':False,'writes_performed':False}
        print(json.dumps(result));return 0
    except Exception:
        print('{"status":"blocked","code":"user_deployment_check_failed_private_config_preserved"}');return 2


if __name__=='__main__':raise SystemExit(main())
