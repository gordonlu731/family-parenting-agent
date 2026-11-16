"""Prepare/apply/revert only this user's temporary fictional preview config.

Never configures Tailscale, changes its policies, or invokes a model.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import urllib.request

sys.path.insert(0,str(Path(__file__).resolve().parent))
import user_service
from deploy import read_env


def candidate(original,origin):
    if not re.fullmatch(r'https://(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.){2,}ts\.net',origin):
        raise ValueError('verified_node_dns_required')
    changes={'PUBLIC_ORIGIN':origin,'COOKIE_SECURE':'true','MODEL_API_KEY':''}
    lines=[];seen=set()
    for line in original.splitlines():
        key=line.partition('=')[0]
        if key in changes:lines.append(key+'='+changes[key]);seen.add(key)
        else:lines.append(line)
    lines.extend(k+'='+v for k,v in changes.items() if k not in seen)
    return '\n'.join(lines)+'\n'


def digest(body):return hashlib.sha256(body.encode()).hexdigest()


def write_private(path,body):
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'w') as f:f.write(body);f.flush();os.fsync(f.fileno())


def prepare(root,data,state,origin):
    user_service.paths(root,data);user_service.environment(root,data)
    user_service.require(not any(p.is_symlink() for p in (state,*state.parents)))
    state.mkdir(mode=0o700,parents=True,exist_ok=True);user_service.owned(state,directory=True)
    original=(root/'.env').read_text();body=candidate(original,origin)
    plan={'root':str(root),'data':str(data),'origin':origin,'original_sha256':digest(original),
          'candidate_sha256':digest(body),'activated':False,'model_disabled_in_candidate':True}
    files={'app.env.before':original,'app.env.preview':body,'app-plan.json':json.dumps(plan,indent=2)+'\n'}
    for name,text in files.items():
        path=state/name
        if path.exists():user_service.owned(path);user_service.require(path.read_text()==text)
        else:write_private(path,text)
    return {'status':'prepared','activated':False,'model_calls':0}


def change(state,restore=False):
    user_service.owned(state,directory=True)
    for name in ('app-plan.json','app.env.before','app.env.preview'):user_service.owned(state/name)
    plan=json.loads((state/'app-plan.json').read_text());root=Path(plan['root']);data=Path(plan['data'])
    user_service.paths(root,data);user_service.owned(root/'.env')
    original=(state/'app.env.before').read_text();preview=(state/'app.env.preview').read_text()
    user_service.require(digest(original)==plan['original_sha256'] and digest(preview)==plan['candidate_sha256'])
    current=(root/'.env').read_text()
    expected=preview if restore else original;target=original if restore else preview
    if current==target:return {'status':'already_restored' if restore else 'already_applied'}
    user_service.require(current==expected)
    def replace(text):
        temp=root/'.env.preview-new';write_private(temp,text);os.replace(temp,root/'.env')
    os.environ['XDG_RUNTIME_DIR']='/run/user/'+str(os.getuid())
    os.environ['DBUS_SESSION_BUS_ADDRESS']='unix:path='+os.environ['XDG_RUNTIME_DIR']+'/bus'
    def restart():subprocess.run(['systemctl','--user','restart',user_service.UNIT],check=True,capture_output=True,timeout=30)
    try:
        replace(target);user_service.environment(root,data);restart()
        import time
        healthy=False
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        for _ in range(20):
            try:
                with opener.open('http://127.0.0.1:18080/api/health',timeout=2) as r:healthy=r.status==200
                if healthy:break
            except Exception:pass
            time.sleep(1)
        user_service.require(healthy)
        if not restore:
            with opener.open('http://127.0.0.1:18080/api/config',timeout=2) as r:
                v=json.loads(r.read());user_service.require(v['model_ready'] is False and v['demo_mode'] is False)
    except Exception:
        replace(expected);restart();raise
    return {'status':'restored' if restore else 'applied','model_calls':0,'database_retained':True}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','apply','restore'])
    p.add_argument('--state',type=Path,required=True);p.add_argument('--root',type=Path);p.add_argument('--data',type=Path);p.add_argument('--origin');a=p.parse_args()
    try:
        os.umask(0o077)
        user_service.require(os.geteuid()!=0)
        if a.action=='prepare':
            user_service.require(a.root is not None and a.data is not None and a.origin is not None)
            result=prepare(a.root,a.data,a.state,a.origin)
        else:result=change(a.state,a.action=='restore')
        print(json.dumps(result));return 0
    except Exception:
        print('{"status":"blocked","code":"preview_config_refused_current_data_preserved"}');return 1


if __name__=='__main__':raise SystemExit(main())
