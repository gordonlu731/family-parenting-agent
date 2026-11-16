"""Prepare a separate private family configuration and reviewed unit, without activating it."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys

sys.path.insert(0,str(Path(__file__).resolve().parent))
import deploy
import user_service as service


def prepare(root,data,backups,state,source,domain=None):
    if domain:
        service.require(bool(re.fullmatch(r'(?=.{1,253}$)(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,63}',domain)))
    root,data=service.paths(root,data)
    service.owned(root,directory=True);service.owned(source)
    service.require(not any(p.is_symlink() for target in (data,backups,state) for p in (target,*target.parents)))
    service.require(data!=backups and data!=state and backups!=state)
    service.require(not any(p.is_relative_to(root) for p in (data,backups,state)))
    for folder in (data,backups,state):
        folder.mkdir(parents=True,mode=0o700,exist_ok=True);service.owned(folder,directory=True)
    service.require(not any(data.iterdir()))  # Never adopt an initialized or ambiguous household.
    values=deploy.read_env(source)
    origin=deploy.https_url('https://'+domain,True) if domain else ''
    config=root/'.env'
    if not config.exists():
        deploy.write_config(config,'production' if domain else 'private',18080,origin=origin,
            base=values.get('MODEL_BASE_URL',deploy.BASE_URL),model=values.get('MODEL_ID',''),
            key=values.get('MODEL_API_KEY',''),thinking=values.get('MODEL_ENABLE_THINKING'),
            daily_limit=values.get('MODEL_DAILY_REQUEST_LIMIT','30'),
            reconfirm_days=values.get('PANTRY_RECONFIRM_DAYS','7'))
    service.owned(config)
    env=service.environment(root,data)
    service.require(env['BOOTSTRAP_TOKEN']!=values.get('BOOTSTRAP_TOKEN'))
    service.require(env['PUBLIC_ORIGIN']==(origin or 'http://127.0.0.1:18080'))
    # Candidate files stay outside the user's active systemd directory.
    candidate=state/'candidate';candidate.mkdir(mode=0o700,exist_ok=True);service.owned(candidate,directory=True)
    unit=candidate/service.UNIT
    if unit.exists():service.owned(unit);service.require(unit.read_text()==service.unit(root,data))
    else:
        with unit.open('x') as f:f.write(service.unit(root,data))
        unit.chmod(0o600)
    if domain:
        proxy=candidate/'Caddyfile'
        body='{\n    admin off\n}\n'+domain+' {\n    reverse_proxy 127.0.0.1:18080\n    encode zstd gzip\n}\n'
        if proxy.exists():service.owned(proxy);service.require(proxy.read_text()==body)
        else:proxy.write_text(body);proxy.chmod(0o600)
    plan={'format':'family-trial-preparation-v1','root':str(root),'data':str(data),'backups':str(backups),
          'domain':domain,'domain_required':not bool(domain),'initialized':False,'activated':False,
          'config_sha256':hashlib.sha256(config.read_bytes()).hexdigest(),
          'next':['confirm_domain_and_dns','administrator_https_proxy_and_ingress_review',
                  'validate_public_https','switch_unit_and_backup_paths_with_rollback',
                  'parent_initializes_new_household','two_wechat_devices']}
    target=state/'plan.json'
    if target.exists():service.owned(target);service.require(json.loads(target.read_text())==plan)
    else:target.write_text(json.dumps(plan,indent=2)+'\n');target.chmod(0o600)
    return {'status':'prepared','activated':False,'initialized':False,'domain_required':not bool(domain)}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for arg in ('root','data','backups','state','source-env'):p.add_argument('--'+arg,type=Path,required=True)
    p.add_argument('--domain');a=p.parse_args()
    try:
        os.umask(0o077)
        # configure prints only fixed status, never credentials.
        result=prepare(a.root,a.data,a.backups,a.state,a.source_env,a.domain)
        print(json.dumps(result));return 0
    except Exception:
        print('{"status":"blocked","code":"trial_preparation_refused_existing_data_preserved"}');return 1


if __name__=='__main__':raise SystemExit(main())
