import importlib
import json
import os
import secrets
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient

mod = importlib.import_module('backend.app')
DAY = datetime.now(ZoneInfo('Asia/Shanghai')).date().isoformat()


class SharedFamilyTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.token = secrets.token_urlsafe(48)
        self.env = patch.dict(os.environ, {'APP_DB': str(Path(self.tmp.name)/'family.db'), 'COOKIE_SECURE':'false','DEMO_MODE':'false','BOOTSTRAP_TOKEN':self.token,'PUBLIC_ORIGIN':'http://testserver','MODEL_API_KEY':'','MODEL_ID':'','MODEL_BASE_URL':''})
        self.env.start()
        self.app = mod.create_app()
        self.owner = TestClient(self.app)
        response = self.owner.post('/api/bootstrap', json={'token': self.token, 'family_name':'测试家庭', 'name':'爸爸'})
        self.assertEqual(response.status_code,200,response.text)
        self.owner.headers['X-CSRF-Token'] = response.json()['csrf']
        self.owner_id = response.json()['member_id']
        self.fid = response.json()['family_id']

    def tearDown(self):
        self.owner.close()
        self.env.stop()
        self.tmp.cleanup()

    def caregiver(self):
        response = self.owner.post('/api/invites',json={})
        self.assertEqual(response.status_code,200,response.text)
        token = response.json()['path'].split('=',1)[1]
        client = TestClient(self.app)
        result = client.post('/api/join',json={'token':token,'name':'外婆'})
        self.assertEqual(result.status_code,200,result.text)
        client.headers['X-CSRF-Token'] = result.json()['csrf']
        self.addCleanup(client.close)
        return client, token, result.json()['member_id']

    def payload(self, **changes):
        return {'day':DAY,'meal':'午餐','items':[{'food':'米饭','amount':'半碗','acceptance':'吃了'},{'food':'牛肉','amount':'未说明','acceptance':'没吃'}], 'note':'', **changes}

    def post_record(self, client=None, payload=None, key=None):
        return (client or self.owner).post('/api/records',json=payload or self.payload(),headers={'Idempotency-Key':key or secrets.token_hex(12)})

    def confirm_profile(self, **changes):
        body = self.owner.get('/api/profile').json()
        body.pop('updated_at')
        body.update(age_months=20,allergy_status='none_known')
        body.update(changes)
        response = self.owner.put('/api/profile',json=body)
        self.assertEqual(response.status_code,200,response.text)
        return response.json()

    def menu_payload(self, **changes):
        return {'day':DAY,'meal':'午餐','title':'时蔬软饭','ingredients':['米饭','青菜'],'method':'充分煮熟','note':'家长核实处理方式','version':0,**changes}

    def test_unauthorized_and_csrf_and_origin(self):
        anon = TestClient(self.app)
        self.addCleanup(anon.close)
        for path in ['/api/profile','/api/members','/api/records','/api/export','/api/messages']:
            self.assertEqual(anon.get(path).status_code,401,path)
        self.assertEqual(self.owner.post('/api/invites',json={},headers={'X-CSRF-Token':'wrong'}).status_code,403)
        self.assertEqual(self.owner.post('/api/invites',json={},headers={'Origin':'https://outside.example'}).status_code,403)

    def test_initialization_one_time_and_cookie_flags(self):
        repeated=self.owner.post('/api/bootstrap',json={'token':self.token,'family_name':'重复','name':'爸爸'})
        self.assertEqual(repeated.status_code,409)
        self.assertEqual(self.owner.get('/api/me').json()['name'],'爸爸')
        self.assertEqual(self.owner.get('/api/profile').headers['cache-control'],'no-store')

    def test_production_demo_disabled(self):
        self.assertEqual(self.owner.post('/api/demo',json={}).status_code,404)

    def test_invite_is_single_use_and_scoped(self):
        client,token,mid=self.caregiver()
        self.assertEqual(client.get('/api/me').json()['family']['id'],self.fid)
        self.assertEqual(self.owner.post('/api/join',json={'token':token,'name':'第二人'}).status_code,403)
        self.assertEqual(client.post('/api/invites',json={}).status_code,403)

    def test_expired_invite_rejected(self):
        r=self.owner.post('/api/invites',json={})
        token=r.json()['path'].split('=',1)[1]
        with mod.database(True) as db:
            db.execute('UPDATE invites SET expires=0')
        self.assertEqual(self.owner.post('/api/join',json={'token':token,'name':'外婆'}).status_code,403)

    def test_two_members_share_records_and_revoke(self):
        grandma,_,mid=self.caregiver()
        saved=self.post_record(grandma)
        self.assertEqual(saved.status_code,200,saved.text)
        records=self.owner.get('/api/records').json()
        self.assertEqual(len(records),1)
        self.assertEqual(records[0]['member_name'],'外婆')
        self.assertEqual(records[0]['items'][1]['acceptance'],'没吃')
        self.assertEqual(self.owner.request('DELETE','/api/members/'+mid,json={}).status_code,200)
        self.assertEqual(grandma.get('/api/records').status_code,401)
        self.assertEqual(len(self.owner.get('/api/records').json()),1)

    def test_idempotency_retries_and_payload_reuse(self):
        key='record-once'
        first=self.post_record(key=key)
        second=self.post_record(key=key)
        self.assertEqual(first.status_code,200,first.text)
        self.assertEqual(first.json()['id'],second.json()['id'])
        self.assertEqual(len(self.owner.get('/api/records').json()),1)
        changed=self.post_record(payload=self.payload(note='改变内容'),key=key)
        self.assertEqual(changed.status_code,409)

    def test_duplicate_meal_requires_explicit_confirmation(self):
        self.assertEqual(self.post_record().status_code,200)
        other,_,_=self.caregiver()
        duplicate=self.post_record(other)
        self.assertEqual(duplicate.status_code,409)
        self.assertEqual(duplicate.json()['detail']['code'],'possible_duplicate')
        confirmed=self.post_record(other,self.payload(confirm_duplicate=True))
        self.assertEqual(confirmed.status_code,200)

    def test_concurrent_retry_creates_one_record(self):
        cookie=self.owner.cookies.get('family_session')
        csrf=self.owner.headers['X-CSRF-Token']
        def save():
            with TestClient(self.app) as client:
                client.cookies.set('family_session',cookie)
                return client.post('/api/records',json=self.payload(),headers={'X-CSRF-Token':csrf,'Idempotency-Key':'concurrent'}).json()
        with ThreadPoolExecutor(max_workers=2) as executor:
            results=list(executor.map(lambda _:save(),range(2)))
        self.assertEqual(results[0]['id'],results[1]['id'])
        self.assertEqual(len(self.owner.get('/api/records').json()),1)

    def test_record_conflict_and_undo_history(self):
        saved=self.post_record().json()
        payload=self.payload(version=1,note='已更正')
        updated=self.owner.put('/api/records/'+saved['id'],json=payload)
        self.assertEqual(updated.status_code,200,updated.text)
        stale=self.owner.put('/api/records/'+saved['id'],json=payload)
        self.assertEqual(stale.status_code,409)
        self.assertEqual(self.owner.post('/api/records/'+saved['id']+'/undo',json={'version':1}).status_code,409)
        self.assertEqual(self.owner.post('/api/records/'+saved['id']+'/undo',json={'version':2}).status_code,200)
        self.assertEqual(self.owner.get('/api/records').json(),[])
        audit=self.owner.get('/api/export').json()['audit']
        self.assertEqual([a['action'] for a in audit],['create','update','undo'])

    def test_cross_family_ids_not_accessible(self):
        saved=self.post_record().json()
        with patch.dict(os.environ,{'DEMO_MODE':'true'}):
            outsider=TestClient(self.app)
            self.addCleanup(outsider.close)
            result=outsider.post('/api/demo',json={}).json()
            outsider.headers['X-CSRF-Token']=result['csrf']
            r=outsider.put('/api/records/'+saved['id'],json=self.payload(version=1))
            self.assertEqual(r.status_code,404)
            names=outsider.get('/api/records').json()
            self.assertTrue(all(x['family_id']!=self.fid for x in names))

    def test_profile_permissions_and_conflict(self):
        p=self.confirm_profile()
        other,_,_=self.caregiver()
        p.pop('updated_at')
        self.assertEqual(other.put('/api/profile',json=p).status_code,403)
        p['version']=1
        self.assertEqual(self.owner.put('/api/profile',json=p).status_code,409)

    def test_menu_requires_profile_and_rejects_known_ingredient(self):
        first=self.owner.put('/api/menus',json=self.menu_payload(),headers={'Idempotency-Key':'first'})
        self.assertEqual(first.status_code,409)
        self.confirm_profile(allergy_status='known',allergies=['花生'])
        blocked=self.owner.put('/api/menus',json=self.menu_payload(title='花生酱软饭'),headers={'Idempotency-Key':'blocked'})
        self.assertEqual(blocked.status_code,422)
        saved=self.owner.put('/api/menus',json=self.menu_payload(),headers={'Idempotency-Key':'save'})
        self.assertEqual(saved.status_code,200,saved.text)
        conflict=self.owner.put('/api/menus',json=self.menu_payload(title='其他菜'),headers={'Idempotency-Key':'conflict'})
        self.assertEqual(conflict.status_code,409)
        same=self.owner.put('/api/menus',json=self.menu_payload(),headers={'Idempotency-Key':'save'})
        self.assertEqual(same.json()['id'],saved.json()['id'])

    def test_messages_are_private_and_ordered(self):
        other,_,mid=self.caregiver()
        with mod.database(True) as db:
            for member_id,text in [(self.owner_id,'爸爸的对话'),(mid,'外婆的对话')]:
                db.execute('INSERT INTO messages VALUES (?,?,?,?,?,?)',(mod.uid(),self.fid,member_id,'user',text,mod.now()))
        self.assertEqual([m['content'] for m in self.owner.get('/api/messages').json()],['爸爸的对话'])
        self.assertEqual([m['content'] for m in other.get('/api/messages').json()],['外婆的对话'])

    def test_profile_change_marks_existing_menu_for_review(self):
        self.confirm_profile()
        saved=self.owner.put('/api/menus',json=self.menu_payload(title='花生软饭',ingredients=['米饭','花生']),headers={'Idempotency-Key':'original-menu'})
        self.assertEqual(saved.status_code,200,saved.text)
        self.confirm_profile(allergy_status='known',allergies=['花生'])
        result=self.owner.get(f'/api/menus?start={DAY}&end={DAY}')
        self.assertTrue(result.json()[0]['review_required'])

    def test_compiled_frontend_is_served_without_auth_data(self):
        if not (mod.ROOT/'dist/index.html').exists():
            self.skipTest('Run npm run build to exercise production static files')
        anonymous=TestClient(self.app)
        self.addCleanup(anonymous.close)
        response=anonymous.get('/')
        self.assertEqual(response.status_code,200)
        self.assertIn('小芽',response.text)
        self.assertNotIn('测试家庭',response.text)
        self.assertIn("frame-ancestors 'none'",response.headers['content-security-policy'])

    def test_configured_model_adapter_is_read_only_with_mock(self):
        class Reply:
            def raise_for_status(self): pass
            def json(self): return {'choices':[{'message':{'content':'可以在记录页面保存午饭情况。'}}]}
        requests=[]
        class Provider:
            def __init__(self,**_): pass
            async def __aenter__(self): return self
            async def __aexit__(self,*_): pass
            async def post(self,url,**kwargs): requests.append(kwargs);return Reply()
        with patch.dict(os.environ,{'MODEL_API_KEY':'test-only-key','MODEL_BASE_URL':'https://model.example/v1','MODEL_ID':'test-model'}),patch.object(mod.httpx,'AsyncClient',Provider):
            r=self.owner.post('/api/assistant',json={'message':'记下午饭吃了米饭'})
        self.assertEqual(r.status_code,200,r.text)
        self.assertFalse(r.json()['saved_records'])
        self.assertEqual(self.owner.get('/api/records').json(),[])
        self.assertEqual(len(self.owner.get('/api/messages').json()),2)
        self.assertNotIn(self.fid,json.dumps(requests[0]['json'],ensure_ascii=False))

    def test_no_model_does_not_pretend_to_save(self):
        self.assertFalse(self.owner.get('/api/config').json()['model_ready'])
        reply=self.owner.post('/api/assistant',json={'message':'记下午饭吃了米饭'})
        self.assertEqual(reply.status_code,503)
        self.assertEqual(self.owner.get('/api/records').json(),[])
        self.assertEqual(self.owner.get('/api/messages').json(),[])

    def test_backup_restore_and_reopen_persistence(self):
        self.post_record()
        target=Path(self.tmp.name)/'backup.db'
        command=[sys.executable,'scripts/manage.py','backup',str(target)]
        result=subprocess.run(command,cwd=mod.ROOT,capture_output=True,text=True,env=os.environ.copy())
        self.assertEqual(result.returncode,0,result.stderr)
        with sqlite3.connect(target) as db:
            self.assertEqual(db.execute('PRAGMA integrity_check').fetchone()[0],'ok')
            self.assertEqual(db.execute('SELECT COUNT(*) FROM records').fetchone()[0],1)
        # A new app instance reads the same persisted database and session.
        reopened=TestClient(mod.create_app())
        self.addCleanup(reopened.close)
        reopened.cookies.set('family_session',self.owner.cookies.get('family_session'))
        self.assertEqual(len(reopened.get('/api/records').json()),1)

    def test_validation_does_not_echo_secret_or_accept_future(self):
        secret='sensitive-test-value'
        r=self.owner.post('/api/bootstrap',json={'token':secret,'family_name':'测试','name':'爸爸'})
        self.assertEqual(r.status_code,422)
        self.assertNotIn(secret,r.text)
        tomorrow=(datetime.now(ZoneInfo('Asia/Shanghai')).date()+timedelta(days=1)).isoformat()
        self.assertEqual(self.post_record(payload=self.payload(day=tomorrow)).status_code,422)


if __name__=='__main__':
    unittest.main()
