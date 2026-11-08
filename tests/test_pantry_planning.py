import json
import os
import secrets
import sqlite3
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
import test_app as base
from test_workflows import provider

mod, DAY = base.mod, base.DAY


class PantryPlanningTest(unittest.TestCase):
    setUp = base.SharedFamilyTest.setUp
    tearDown = base.SharedFamilyTest.tearDown
    caregiver = base.SharedFamilyTest.caregiver
    confirm_profile = base.SharedFamilyTest.confirm_profile
    payload = base.SharedFamilyTest.payload
    post_record = base.SharedFamilyTest.post_record
    menu_payload = base.SharedFamilyTest.menu_payload

    def item(self, **changes):
        return {'version': 0, 'name': '大米', 'quantity': '30', 'unit': '克', 'amount_note': '',
                'location': '常温', 'kind': 'raw', 'status': 'available', **changes}

    def stock(self, client=None):
        return (client or self.owner).get('/api/pantry').json()

    def put(self, items, version=None, key=None, client=None, **changes):
        client = client or self.owner
        body = {'version': self.stock(client)['version'] if version is None else version,
                'items': items, 'review_confirmed': True, **changes}
        return client.put('/api/pantry', json=body, headers={'Idempotency-Key': key or secrets.token_hex(12)})

    def add(self, **changes):
        result = self.put([self.item(**changes)])
        self.assertEqual(result.status_code, 200, result.text)
        return next(i for i in self.stock()['items'] if i['id']==result.json()['item_ids'][0])

    def editable_item(self, value, **changes):
        fields = ('id','version','name','quantity','unit','amount_note','location','kind','status')
        return {**{k: value[k] for k in fields}, **changes}

    def output(self, **changes):
        return {'meals': [{'day': DAY, 'meal': '午餐', 'title': '蔬菜软饭',
                           'ingredients': [{'name': '大米', 'quantity': '20', 'unit': '克'},
                                           {'name': '青菜', 'quantity': '10', 'unit': '克'}],
                           'method': '食材充分煮熟，处理成合适的质地。', 'note': ''}],
                'rationale': '参考已确认资料，待家长核对。', **changes}

    def generate(self, output=None, **changes):
        with provider(json.dumps(output or self.output(), ensure_ascii=False)) as calls:
            response = self.owner.post('/api/menu-proposals', json={'start': DAY, 'days': 1, 'meals': ['午餐'], **changes},
                                       headers={'Idempotency-Key': secrets.token_hex(12)})
        return response, calls

    def confirm(self, proposal, client=None, **changes):
        return (client or self.owner).post('/api/proposals/'+proposal['id']+'/confirm',
                                           json={'version': proposal['version'], 'review_confirmed': True, **changes})

    def shopping(self):
        response = self.owner.get('/api/shopping', params={'start': DAY, 'end': DAY})
        self.assertEqual(response.status_code, 200, response.text)
        return {i['name']: i for i in response.json()['items']}

    def extraction(self, **changes):
        return {'intent': 'actual_inventory', 'items': [{'name': '番茄', 'quantity': '2', 'unit': '个',
                'amount_note': '', 'location': '冷藏', 'kind': 'raw', 'status': 'available', 'evidence': '冷藏还有2个番茄'}],
                'questions': [], **changes}

    def extract(self, output=None, text='冷藏还有2个番茄', key=None):
        with provider(json.dumps(output or self.extraction(), ensure_ascii=False)):
            return self.owner.post('/api/pantry-proposals', json={'text': text}, headers={'Idempotency-Key': key or secrets.token_hex(12)})

    def test_shared_inventory_confirmation_idempotency_and_export(self):
        grandma, _, _ = self.caregiver()
        item = self.item()
        self.assertEqual(self.put([item], review_confirmed=False).status_code, 422)
        first = self.put([item], version=0, key='same-stock', client=grandma)
        second = self.put([item], version=0, key='same-stock', client=grandma)
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(first.json(), second.json())
        self.assertEqual(self.stock()['version'], 1)
        self.assertEqual(len(self.stock()['items']), 1)
        self.assertEqual(self.stock()['items'][0]['member_name'], '外婆')
        self.assertEqual(self.stock()['items'][0]['quantity'], '30')
        self.assertEqual(len(self.owner.get('/api/export').json()['pantry']), 1)
        self.assertEqual(self.owner.get('/api/pantry').headers['cache-control'], 'no-store')

    def test_atomic_batch_and_optimistic_conflicts(self):
        old = self.add()
        self.assertEqual(self.put([self.item(name='番茄')], version=0).status_code, 409)
        update = self.editable_item(old, quantity='50')
        before = self.stock()
        result = self.put([update, self.item()])  # Duplicate target key, before or during write.
        self.assertEqual(result.status_code, 422)
        self.assertEqual(self.stock(), before)
        result = self.put([self.item(name='先创建的食材'), self.item(id=old['id'], version=99)])
        self.assertEqual(result.status_code, 409)
        self.assertEqual(self.stock(), before)  # Earlier insert is rolled back too.
        self.assertEqual(self.put([update]).status_code, 200)
        self.assertEqual(self.put([update]).status_code, 409)

    def test_same_name_normalization_location_and_raw_cooked_separation(self):
        self.add(name='ＴＯＭＡＴＯ')
        self.assertEqual(self.put([self.item(name='tomato')]).status_code, 409)
        self.add(name='tomato', location='冷冻')
        self.add(name='tomato', kind='cooked')
        self.assertEqual(len(self.stock()['items']), 3)

    def test_unknown_amount_used_up_and_restore(self):
        old = self.add(quantity=None, unit='适量', amount_note='还剩一点')
        self.assertIsNone(old['quantity'])
        used = self.put([self.editable_item(old, status='used_up')])
        self.assertEqual(used.status_code, 200)
        updated = self.stock()['items'][0]
        self.assertEqual(updated['status'], 'used_up')
        self.assertIsNone(updated['quantity'])
        self.assertEqual(self.put([self.editable_item(updated, status='available', quantity='10', unit='克')]).status_code, 200)
        self.assertEqual(self.stock()['items'][0]['quantity'], '10')

    def test_inventory_auth_scope_csrf_and_revoked_membership(self):
        old = self.add()
        with TestClient(self.app) as anon:
            self.assertEqual(anon.get('/api/pantry').status_code, 401)
        with patch.dict(os.environ, {'DEMO_MODE': 'true'}), TestClient(self.app) as outsider:
            auth = outsider.post('/api/demo', json={}).json()
            outsider.headers['X-CSRF-Token'] = auth['csrf']
            self.assertEqual(self.stock(outsider)['items'], [])
            self.assertEqual(self.put([self.editable_item(old)], client=outsider).status_code, 404)
        grandma, _, mid = self.caregiver()
        self.owner.request('DELETE', '/api/members/'+mid, json={})
        self.assertEqual(grandma.get('/api/pantry').status_code, 401)
        self.assertEqual(self.owner.put('/api/pantry', json={}, headers={'X-CSRF-Token': 'wrong'}).status_code, 403)

    def test_quantity_and_field_validation(self):
        for changes in ({'quantity':'-1'}, {'quantity':'0'}, {'quantity':None,'unit':'克'}, {'quantity':'2','unit':'斤'}, {'family_id':'outside'}, {'location':'模型猜的位置'}):
            self.assertEqual(self.put([self.item(**changes)]).status_code, 422, changes)
        self.assertEqual(self.stock()['items'], [])

    def test_inventory_ai_draft_is_private_editable_and_explicit(self):
        grandma, _, _ = self.caregiver()
        p = self.extract(key='stock-once').json()['proposal']
        self.assertEqual(self.extract(key='stock-once').json()['proposal']['id'], p['id'])
        self.assertEqual(self.owner.get('/api/ai-usage').json()['calls'], 1)
        self.assertEqual(p['kind'], 'pantry')
        self.assertEqual(self.stock()['items'], [])
        self.assertEqual(self.confirm(p, review_confirmed=False).status_code, 422)
        self.assertEqual(self.confirm(p, client=grandma).status_code, 404)
        payload = p['payload']; payload['items'][0]['quantity'] = '3'
        edited = self.owner.put('/api/proposals/'+p['id'], json={'version': 1, 'payload': payload})
        self.assertEqual(edited.status_code, 200, edited.text)
        self.assertEqual(self.confirm(p).status_code, 409)
        p = edited.json()
        self.assertEqual(self.confirm(p).status_code, 200)
        self.assertEqual(self.confirm(p).status_code, 200)
        self.assertEqual(self.stock(grandma)['items'][0]['quantity'], '3')
        self.assertEqual(self.stock()['version'], 1)

    def test_inventory_ai_plan_and_unfounded_food_do_not_write(self):
        with provider(json.dumps(self.extraction())) as calls:
            response = self.owner.post('/api/pantry-proposals', json={'text':'明天打算买番茄'})
        self.assertIsNone(response.json()['proposal'])
        self.assertEqual(calls, [])
        wrong = self.extraction(); wrong['items'][0]['name'] = '苹果'
        self.assertEqual(self.extract(wrong).status_code, 502)
        self.assertEqual(self.stock()['items'], [])

    def test_inventory_ai_unknown_number_and_ambiguous_location(self):
        out = self.extraction(); out['items'][0].update(evidence='冷藏还有两个番茄')
        p = self.extract(out, text='冷藏还有两个番茄').json()['proposal']
        self.assertIsNone(p['payload']['items'][0]['quantity'])
        self.assertIn('两个', p['payload']['items'][0]['amount_note'])
        out['items'][0]['evidence']='冷藏还有12个番茄'
        wrong_number=self.extract(out,text='冷藏还有12个番茄').json()['proposal']
        self.assertIsNone(wrong_number['payload']['items'][0]['quantity'])
        self.add(name='番茄', location='冷藏'); self.add(name='番茄', location='冷冻')
        out['items'][0].update(location='未说明', evidence='番茄已经用完了', status='used_up', quantity=None, unit='适量')
        result = self.extract(out, text='番茄已经用完了').json()
        self.assertIsNone(result['proposal'])
        self.assertIn('多个位置', result['questions'][0])

    def test_inventory_draft_stale_and_expired_fail_without_partial_update(self):
        p = self.extract().json()['proposal']
        self.add()
        self.assertEqual(self.confirm(p).status_code, 409)
        self.assertEqual([i['name'] for i in self.stock()['items']], ['大米'])
        p = self.extract().json()['proposal']
        with mod.database(True) as db: db.execute('UPDATE proposals SET expires=0 WHERE id=?', (p['id'],))
        self.assertEqual(self.confirm(p).status_code, 409)

    def test_recommendation_uses_distinct_history_actual_and_stock_without_ids(self):
        self.confirm_profile()
        yesterday = (date.fromisoformat(DAY)-timedelta(days=1)).isoformat()
        self.owner.put('/api/menus', json=self.menu_payload(day=yesterday), headers={'Idempotency-Key':'past-menu'})
        self.post_record(payload=self.payload(day=yesterday))
        self.add()
        self.add(name='熟食只用于登记', kind='cooked')
        response, calls = self.generate(self.output(basis=['R1','M1','P1']))
        self.assertEqual(response.status_code, 200, response.text)
        sent = json.loads(calls[0]['messages'][1]['content'])['family_context']
        self.assertEqual(sent['history_menus'][0]['title'], '时蔬软饭')
        self.assertEqual(sent['records'][0]['items'][1]['acceptance'], '没吃')
        self.assertEqual([i['name'] for i in sent['pantry']], ['大米'])
        self.assertEqual(sent['coverage']['excluded_stock_items'], 1)
        serialized = json.dumps(sent)
        self.assertNotIn(self.fid, serialized)
        self.assertNotIn(self.owner_id, serialized)
        self.assertEqual(response.json()['context']['period']['end'], DAY)

    def test_changed_inventory_blocks_stale_menu_and_false_basis_is_rejected(self):
        self.confirm_profile(); old = self.add()
        p = self.generate(self.output(basis=['P1']))[0].json()
        self.put([self.editable_item(old, quantity='10')])
        self.assertEqual(self.confirm(p).status_code, 409)
        self.assertEqual(self.owner.get('/api/menus', params={'start':DAY,'end':DAY}).json(), [])
        response, _ = self.generate(self.output(basis=['P999']))
        self.assertEqual(response.status_code, 502)
        p = self.generate()[0].json(); altered = p['payload']; altered['basis']=['P999']
        self.assertEqual(self.owner.put('/api/proposals/'+p['id'], json={'version':1,'payload':altered}).status_code, 422)

    def test_context_coverage_reports_truncation_and_excludes_used_or_stale(self):
        self.confirm_profile(); self.add(status='used_up')
        stale = self.add(name='老库存')
        with mod.database(True) as db:
            db.execute('UPDATE pantry SET confirmed_at=? WHERE id=?', ((datetime.now(mod.TZ)-timedelta(days=8)).isoformat(), stale['id']))
            for _ in range(17):
                db.execute('INSERT INTO records VALUES (?,?,?,?,?,?,?,1,0,?,?)', (mod.uid(),self.fid,self.owner_id,DAY,'午餐','[]','',mod.now(),mod.now()))
        response, calls = self.generate()
        self.assertEqual(response.status_code, 200, response.text)
        context = response.json()['context']
        self.assertTrue(context['coverage']['truncated'])
        self.assertEqual(context['coverage']['total_records'], 17)
        self.assertLessEqual(context['coverage']['records_included'], 14)
        self.assertEqual(context['pantry'], [])

    def test_shopping_sums_multiple_meals_before_one_inventory_deduction(self):
        self.confirm_profile(); self.add(quantity='30')
        output = self.output(); output['meals'].append({**output['meals'][0], 'meal':'晚餐'})
        response, _ = self.generate(output, meals=['午餐','晚餐'])
        self.assertEqual(self.confirm(response.json()).status_code, 200)
        rice = self.shopping()['大米']
        self.assertEqual(rice['quantity'], '4E+1')
        self.assertEqual(rice['buy_quantity'], '1E+1')
        self.assertEqual(rice['category'], 'need_buy')
        self.assertEqual(self.stock()['items'][0]['quantity'], '30')
        self.post_record()
        self.assertEqual(self.stock()['items'][0]['quantity'], '30')

    def test_shopping_enough_unknown_unit_mismatch_cooked_and_stale(self):
        self.confirm_profile()
        self.add(quantity='50'); self.add(name='青菜', quantity=None, unit='适量', amount_note='还有一点')
        self.assertEqual(self.confirm(self.generate()[0].json()).status_code, 200)
        result = self.shopping()
        self.assertEqual(result['大米']['category'], 'enough')
        self.assertEqual(result['大米']['buy_quantity'], '0')
        self.assertEqual(result['青菜']['category'], 'check')
        for item in self.stock()['items']:
            self.put([self.editable_item(item, status='used_up')])
        # Reactivate rice with an incompatible unit and vegetables as cooked food.
        for item in self.stock()['items']:
            self.put([self.editable_item(item, status='available', unit='个', quantity='2', kind='cooked' if item['name']=='青菜' else 'raw')])
        result = self.shopping()
        self.assertEqual(result['大米']['category'], 'check')
        self.assertEqual(result['青菜']['category'], 'need_buy')
        rice = next(i for i in self.stock()['items'] if i['name']=='大米')
        self.put([self.editable_item(rice, unit='克', quantity='100')])
        with mod.database(True) as db: db.execute('UPDATE pantry SET confirmed_at=? WHERE name=?', ((datetime.now(mod.TZ)-timedelta(days=8)).isoformat(), '大米'))
        self.assertEqual(self.shopping()['大米']['category'], 'check')

    def test_unknown_recipe_amount_does_not_claim_stock_is_enough(self):
        self.confirm_profile(); self.add(quantity='100')
        output = self.output(); output['meals'][0]['ingredients'][0].update(quantity=None, unit='适量')
        self.confirm(self.generate(output)[0].json())
        self.assertEqual(self.shopping()['大米']['category'], 'check')
        self.assertIsNone(self.shopping()['大米']['buy_quantity'])
        self.add(name='南瓜', quantity='2', unit='份')
        output['meals'][0]['ingredients']=[{'name':'南瓜','quantity':'1','unit':'份'}]
        self.confirm(self.generate(output)[0].json())
        self.assertEqual(self.shopping()['南瓜']['category'], 'check')

    def test_chat_uses_shared_context_without_claiming_inventory_writes(self):
        self.confirm_profile(); self.add()
        self.post_record()
        tomorrow=(date.fromisoformat(DAY)+timedelta(days=1)).isoformat()
        self.owner.put('/api/menus',json=self.menu_payload(day=tomorrow,title='明天已有安排'),headers={'Idempotency-Key':'tomorrow-menu'})
        before = self.stock()
        with provider('现有原料可作参考，菜单仍需核对。') as calls:
            result = self.owner.post('/api/assistant', json={'message':'根据家里食材推荐下一餐'}, headers={'Idempotency-Key':'chat-stock'})
        self.assertEqual(result.status_code, 200, result.text)
        self.assertFalse(result.json()['saved_records'])
        self.assertIn('大米', calls[0]['messages'][0]['content'])
        self.assertIn('明天已有安排', calls[0]['messages'][0]['content'])
        self.assertIn('没吃', calls[0]['messages'][0]['content'])
        self.assertEqual(self.stock(), before)

    def test_stock_aging_while_draft_waits_requires_reconfirmation(self):
        self.confirm_profile(); self.add()
        p = self.generate()[0].json()
        with patch('backend.workflows.datetime') as clock:
            clock.now.return_value = datetime.now(mod.TZ)+timedelta(days=7)
            result = self.confirm(p)
        self.assertEqual(result.status_code, 409)
        self.assertIn('重新确认', result.text)

    def test_full_two_member_menu_buy_feedback_review_and_replacement(self):
        self.confirm_profile(); self.add(quantity='10')
        grandma, _, _ = self.caregiver()
        p = self.generate()[0].json()
        self.assertEqual(self.confirm(p).status_code, 200)
        self.assertEqual(self.shopping()['大米']['category'], 'need_buy')
        rice = self.stock(grandma)['items'][0]
        self.assertEqual(self.put([self.editable_item(rice, quantity='30')], client=grandma).status_code, 200)
        self.assertEqual(self.shopping()['大米']['category'], 'enough')
        self.post_record(grandma, self.payload(items=[{'food':'实际改吃小米粥','amount':'几口','acceptance':'吃了一些'}]))
        review = self.owner.get('/api/review', params={'start':DAY,'end':DAY}).json()
        self.assertEqual(review['days'][0]['meals'][1]['records'][0]['member_name'], '外婆')
        second, calls = self.generate()
        self.assertIn('实际改吃小米粥', json.dumps(calls[0]['messages'], ensure_ascii=False))
        replacement = self.output(); replacement['meals'][0].update(title='南瓜粥', ingredients=[{'name':'南瓜','quantity':'20','unit':'克'}])
        p, _ = self.generate(replacement, replace=True)
        self.assertEqual(self.confirm(p.json()).status_code, 200)
        self.assertEqual(set(self.shopping()), {'南瓜'})
        self.assertEqual(self.stock()['items'][0]['quantity'], '30')

    def test_migration_from_v2_preserves_records_and_backup_reopens_inventory(self):
        legacy = Path(self.tmp.name)/'legacy.db'
        root = Path(mod.ROOT)
        with sqlite3.connect(legacy) as db:
            db.executescript((root/'backend/schema.sql').read_text()+(root/'backend/migrations/002_ai_workflows.sql').read_text())
            db.execute('INSERT INTO schema_migrations VALUES (2,CURRENT_TIMESTAMP)')
            db.execute('INSERT INTO proposals (id,family_id,member_id,kind,payload,source_text,profile_version,base_versions,expires,created_at) VALUES (?,?,?,?,?,?,?,?,?,?)',('old-proposal','legacy','old-member','record','{}','虚构旧草稿',1,'{}',9999999999,mod.now()))
            db.execute('INSERT INTO families VALUES (?,?,?)', ('legacy','虚构旧家庭',mod.now()))
            db.execute('INSERT INTO members VALUES (?,?,?,?,1,?)', ('old-member','legacy','家长','owner',mod.now()))
            db.execute('INSERT INTO records VALUES (?,?,?,?,?,?,?,1,0,?,?)', ('old-record','legacy','old-member',DAY,'午餐','[]','旧数据保留',mod.now(),mod.now()))
        with patch.dict(os.environ, {'APP_DB':str(legacy)}):
            mod.create_app()
            with mod.database() as db:
                self.assertEqual(db.execute('SELECT note FROM records').fetchone()[0], '旧数据保留')
                self.assertEqual(db.execute('SELECT context_snapshot FROM proposals').fetchone()[0], '{}')
                self.assertEqual([r[0] for r in db.execute('SELECT version FROM schema_migrations ORDER BY version')], [1,2,3])
                self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(), [])
        self.add()
        source = Path(self.tmp.name)/'family.db'; restored = Path(self.tmp.name)/'restore.db'
        with sqlite3.connect(source) as src, sqlite3.connect(restored) as dst: src.backup(dst)
        with patch.dict(os.environ, {'APP_DB':str(restored)}):
            mod.create_app()
            with mod.database() as db:
                self.assertEqual(db.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
                self.assertEqual(db.execute('SELECT name FROM pantry').fetchone()[0], '大米')
