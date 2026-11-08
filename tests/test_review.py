import json
import os
import unittest
from datetime import date, timedelta
from unittest.mock import patch

from fastapi.testclient import TestClient
import test_app as base

mod, DAY = base.mod, base.DAY


class ReviewTest(unittest.TestCase):
    setUp = base.SharedFamilyTest.setUp
    tearDown = base.SharedFamilyTest.tearDown
    caregiver = base.SharedFamilyTest.caregiver
    confirm_profile = base.SharedFamilyTest.confirm_profile
    payload = base.SharedFamilyTest.payload
    post_record = base.SharedFamilyTest.post_record
    menu_payload = base.SharedFamilyTest.menu_payload

    def review(self, start=DAY, end=DAY, client=None):
        return (client or self.owner).get('/api/review', params={'start': start, 'end': end})

    def save_menu(self, **changes):
        response = self.owner.put('/api/menus', json=self.menu_payload(**changes),
                                  headers={'Idempotency-Key': mod.uid()})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_plan_only_does_not_become_actual_or_change_data(self):
        self.confirm_profile()
        self.save_menu()
        with mod.database() as db:
            before = {name: db.execute('SELECT COUNT(*) FROM '+name).fetchone()[0]
                      for name in ('records', 'menus', 'audit', 'ai_usage')}
        response = self.review()
        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()
        lunch = result['days'][0]['meals'][1]
        self.assertEqual(lunch['menu']['title'], '时蔬软饭')
        self.assertEqual(lunch['records'], [])
        self.assertFalse(lunch['has_records'])
        self.assertEqual(result['summary'], {'planned_meals': 1, 'recorded_meals': 0,
                                           'record_count': 0, 'unrecorded_main_meals': 3})
        self.assertIn('未记录不等于没吃', result['note'])
        with mod.database() as db:
            after = {name: db.execute('SELECT COUNT(*) FROM '+name).fetchone()[0] for name in before}
        self.assertEqual(before, after)

    def test_actual_changes_and_multiple_people_do_not_inflate_meal_count(self):
        self.confirm_profile()
        self.save_menu()
        grandma, _, _ = self.caregiver()
        actual = self.post_record(grandma, self.payload(items=[{'food': '南瓜粥', 'amount': '几口', 'acceptance': '吃了一些'}])).json()
        extra = self.post_record(payload=self.payload(confirm_duplicate=True)).json()
        result = self.review().json()
        lunch = result['days'][0]['meals'][1]
        self.assertEqual(lunch['menu']['title'], '时蔬软饭')
        self.assertEqual({r['id'] for r in lunch['records']}, {actual['id'], extra['id']})
        self.assertEqual({r['member_name'] for r in lunch['records']}, {'爸爸', '外婆'})
        self.assertIn('南瓜粥', json.dumps(lunch, ensure_ascii=False))
        self.assertEqual(result['summary']['record_count'], 2)
        self.assertEqual(result['summary']['recorded_meals'], 1)
        self.assertEqual(result['summary']['unrecorded_main_meals'], 2)

    def test_backfill_correction_move_and_undo_use_current_facts(self):
        yesterday = (date.fromisoformat(DAY)-timedelta(days=1)).isoformat()
        original = self.post_record(payload=self.payload(day=yesterday, meal='加餐')).json()
        result = self.review(start=yesterday).json()
        self.assertEqual([d['day'] for d in result['days']], [DAY, yesterday])
        self.assertEqual(result['summary']['recorded_meals'], 1)
        self.assertEqual(result['summary']['unrecorded_main_meals'], 6)
        changed = self.owner.put('/api/records/'+original['id'], json=self.payload(
            version=1, day=DAY, meal='早餐', items=[{'food': '米饭', 'amount': '未说明', 'acceptance': '没吃'}]))
        self.assertEqual(changed.status_code, 200, changed.text)
        result = self.review(start=yesterday).json()
        self.assertFalse(result['days'][1]['meals'][3]['has_records'])
        breakfast = result['days'][0]['meals'][0]
        self.assertTrue(breakfast['has_records'])  # A refusal is still a recorded observation.
        self.assertEqual(breakfast['records'][0]['items'][0]['acceptance'], '没吃')
        self.assertEqual(breakfast['records'][0]['version'], 2)
        self.assertEqual(self.owner.post('/api/records/'+original['id']+'/undo', json={'version': 2}).status_code, 200)
        self.assertEqual(self.review(start=yesterday).json()['summary']['record_count'], 0)

    def test_menu_revisions_never_rewrite_actual_foods(self):
        self.confirm_profile()
        self.save_menu()
        self.post_record()
        self.save_menu(title='修改后的菜单', ingredients=['南瓜'], version=1)
        lunch = self.review().json()['days'][0]['meals'][1]
        self.assertEqual(lunch['menu']['title'], '修改后的菜单')
        self.assertEqual(lunch['records'][0]['items'][0]['food'], '米饭')

    def test_household_isolation_authentication_and_revocation(self):
        self.post_record()
        with TestClient(self.app) as anonymous:
            self.assertEqual(self.review(client=anonymous).status_code, 401)
        grandma, _, mid = self.caregiver()
        self.assertEqual(self.review(client=grandma).json()['summary']['record_count'], 1)
        with patch.dict(os.environ, {'DEMO_MODE': 'true'}), TestClient(self.app) as outsider:
            outsider.post('/api/demo', json={})
            data = self.review(client=outsider).json()
            for day in data['days']:
                for slot in day['meals']:
                    self.assertTrue(all(r['family_id'] != self.fid for r in slot['records']))
                    if slot['menu']:
                        self.assertNotEqual(slot['menu']['family_id'], self.fid)
        self.owner.request('DELETE', '/api/members/'+mid, json={})
        self.assertEqual(self.review(client=grandma).status_code, 401)
        self.assertEqual(self.review().headers['cache-control'], 'no-store')

    def test_range_boundaries_and_future_dates(self):
        day = date.fromisoformat(DAY)
        self.assertEqual(self.review(start=(day-timedelta(days=30)).isoformat()).status_code, 200)
        self.assertEqual(self.review(start=(day-timedelta(days=31)).isoformat()).status_code, 422)
        self.assertEqual(self.review(start=DAY, end=(day-timedelta(days=1)).isoformat()).status_code, 422)
        self.assertEqual(self.review(end=(day+timedelta(days=1)).isoformat()).status_code, 422)
        self.assertEqual(self.review(start='invalid').status_code, 422)

    def test_excess_records_are_not_silently_truncated(self):
        stamp = mod.now()
        with mod.database(True) as db:
            db.executemany('INSERT INTO records VALUES (?,?,?,?,?,?,?,1,0,?,?)',
                           [(mod.uid(), self.fid, self.owner_id, DAY, '午餐', '[]', '', stamp, stamp)
                            for _ in range(1001)])
        response = self.review()
        self.assertEqual(response.status_code, 422)
        self.assertIn('缩短日期范围', response.text)
