import unittest
from fastapi.testclient import TestClient
import test_app as base

class LoginFlowTest(unittest.TestCase):
    setUp=base.SharedFamilyTest.setUp
    tearDown=base.SharedFamilyTest.tearDown
    caregiver=base.SharedFamilyTest.caregiver
    post_record=base.SharedFamilyTest.post_record
    payload=base.SharedFamilyTest.payload

    def test_returning_browser_keeps_identity_without_invite(self):
        family,_,mid=self.caregiver()
        with TestClient(self.app) as returning:
            returning.cookies.update(family.cookies)
            self.assertEqual(returning.get('/api/me').json()['id'],mid)

    def test_recovery_preview_does_not_consume_and_keeps_original_identity(self):
        family,_,mid=self.caregiver()
        self.post_record(family)
        token=self.owner.post('/api/invites',json={'member_id':mid}).json()['path'].split('=',1)[1]
        family.post('/api/logout',json={})
        with TestClient(self.app) as device:
            preview=device.post('/api/invite-preview',json={'token':token})
            self.assertEqual(preview.status_code,200)
            self.assertEqual(preview.json()['member_name'],'外婆')
            self.assertEqual(preview.json()['kind'],'login')
            self.assertEqual(device.get('/api/records').status_code,401)
            joined=device.post('/api/join',json={'token':token})
            self.assertEqual(joined.status_code,200,joined.text)
            self.assertEqual(device.get('/api/me').json()['id'],mid)
            self.assertEqual(device.get('/api/me').json()['name'],'外婆')
            self.assertEqual(device.get('/api/records').json()[0]['member_id'],mid)
            self.assertEqual(device.post('/api/invite-preview',json={'token':token}).status_code,403)
        self.assertEqual(len(self.owner.get('/api/members').json()),2)

    def test_new_member_still_requires_name_and_preview_is_minimal(self):
        token=self.owner.post('/api/invites',json={}).json()['path'].split('=',1)[1]
        with TestClient(self.app) as device:
            preview=device.post('/api/invite-preview',json={'token':token}).json()
            self.assertEqual(set(preview),{'family_name','member_name','kind'})
            self.assertEqual(preview['kind'],'join')
            self.assertEqual(device.post('/api/join',json={'token':token}).status_code,422)
            self.assertEqual(device.post('/api/join',json={'token':token,'name':'爷爷'}).status_code,200)

    def test_revocation_blocks_unconsumed_recovery_link(self):
        _,_,mid=self.caregiver()
        token=self.owner.post('/api/invites',json={'member_id':mid}).json()['path'].split('=',1)[1]
        self.owner.request('DELETE','/api/members/'+mid,json={})
        with TestClient(self.app) as device:
            self.assertEqual(device.post('/api/invite-preview',json={'token':token}).status_code,403)
            self.assertEqual(device.post('/api/join',json={'token':token}).status_code,403)

    def test_preview_expiry_and_origin_are_enforced(self):
        token=self.owner.post('/api/invites',json={}).json()['path'].split('=',1)[1]
        with TestClient(self.app) as device:
            self.assertEqual(device.post('/api/invite-preview',json={'token':token},headers={'Origin':'https://wrong.example'}).status_code,403)
            with base.mod.database(True) as db:db.execute('UPDATE invites SET expires=0')
            self.assertEqual(device.post('/api/invite-preview',json={'token':token}).status_code,403)
