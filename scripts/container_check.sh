#!/usr/bin/env bash
# Disposable CI-only container and volume. Never points at ECS or existing data.
set -euo pipefail
if [[ "${GITHUB_ACTIONS:-}" != "true" ]]; then
  printf '%s\n' 'This disposable check is restricted to GitHub CI; do not run it on ECS.' >&2
  exit 2
fi
qa_docker() {
  env -u DOCKER_HOST -u DOCKER_CONTEXT -u DOCKER_TLS -u DOCKER_TLS_VERIFY -u DOCKER_CERT_PATH \
    docker --host=unix:///var/run/docker.sock "$@"
}
cd "$(dirname "$0")/.."
qa_suffix=$(python3 -c 'import secrets; print(secrets.token_hex(6))')
qa_container="family-qa-${qa_suffix}"
qa_volume="family-qa-data-${qa_suffix}"
qa_image="family-parenting-agent:qa-${qa_suffix}"
qa_bootstrap=$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')
cleanup() {
  qa_docker rm -f "$qa_container" >/dev/null 2>&1 || true
  qa_docker volume rm "$qa_volume" >/dev/null 2>&1 || true
}
trap cleanup EXIT
qa_docker build --tag "$qa_image" .
qa_docker volume create "$qa_volume" >/dev/null
qa_docker run --detach --name "$qa_container" --memory=384m --cpus=0.75 \
  --security-opt=no-new-privileges:true --mount "source=${qa_volume},target=/data" \
  --env "BOOTSTRAP_TOKEN=${qa_bootstrap}" "$qa_image" >/dev/null
wait_ready() {
  for attempt in $(seq 1 30); do
    if qa_docker exec "$qa_container" python -c 'import urllib.request; urllib.request.urlopen("http://127.0.0.1:8000/api/health", timeout=2)' >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done
  qa_docker logs "$qa_container"
  return 1
}
wait_ready
qa_docker exec -i "$qa_container" python - <<'PY'
import datetime,http.cookies,json,os,urllib.request
from zoneinfo import ZoneInfo
origin='http://127.0.0.1:8000'
body=json.dumps({'token':os.environ['BOOTSTRAP_TOKEN'],'family_name':'虚构容器验收','name':'测试家长'}).encode()
response=urllib.request.urlopen(urllib.request.Request(origin+'/api/bootstrap',data=body,headers={'Content-Type':'application/json'}))
session=http.cookies.SimpleCookie(response.headers['Set-Cookie'])
auth=json.loads(response.read())
# Internal backend HTTP only. This does not test HTTPS or browser Secure cookies.
record={'day':datetime.datetime.now(ZoneInfo('Asia/Shanghai')).date().isoformat(),'meal':'午餐','items':[{'food':'虚构软饭','amount':'几口','acceptance':'吃了一些'}],'note':'仅CI测试'}
headers={'Content-Type':'application/json','Cookie':'family_session='+session['family_session'].value,'X-CSRF-Token':auth['csrf'],'Idempotency-Key':'container-fixture'}
assert urllib.request.urlopen(urllib.request.Request(origin+'/api/records',data=json.dumps(record).encode(),headers=headers)).status==200
print('Seeded one fictional record through private container HTTP.')
PY
qa_backup_result=$(qa_docker exec "$qa_container" python scripts/operations.py backup --source /data/family.sqlite3 --destination /data/backups --keep 14)
qa_backup_name=$(python3 -c 'import json,sys; print(json.loads(sys.argv[1])["backup"])' "$qa_backup_result")
qa_docker exec "$qa_container" python scripts/operations.py restore-check --backup "/data/backups/${qa_backup_name}"
qa_docker exec "$qa_container" python scripts/operations.py check --source /data/family.sqlite3 --backup-dir /data/backups
qa_docker exec "$qa_container" python scripts/evaluate.py --mock-model --cases r01,r03,m01,p01
qa_docker restart "$qa_container" >/dev/null
wait_ready
qa_docker exec "$qa_container" python -c 'import sqlite3; db=sqlite3.connect("/data/family.sqlite3"); assert db.execute("SELECT COUNT(*) FROM records").fetchone()[0]==1; assert db.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0]==3; print("Container restart preserved fictional record and schema.")'
