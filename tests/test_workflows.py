import json
import os
import secrets
import unittest
from contextlib import contextmanager
from decimal import Decimal
from unittest.mock import patch

import test_app as base

mod,DAY=base.mod,base.DAY


@contextmanager
def provider(output,fail=False):
    calls=[]
    class Reply:
        def raise_for_status(self):
            if fail:raise mod.httpx.ConnectError('provider unavailable')
        def json(self):
            return {'choices':[{'message':{'content':output},'finish_reason':'stop'}],'usage':{'prompt_tokens':400,'completion_tokens':100}}
    class Client:
        def __init__(self,**_):pass
        async def __aenter__(self):return self
        async def __aexit__(self,*_):pass
        async def post(self,url,**kwargs):calls.append(kwargs['json']);return Reply()
    with patch.dict(os.environ,{'MODEL_API_KEY':'test-key','MODEL_BASE_URL':'https://model.example/v1','MODEL_ID':'test-model','MODEL_DAILY_REQUEST_LIMIT':'30'}),patch.object(mod.httpx,'AsyncClient',Client):
        yield calls


class WorkflowTest(unittest.TestCase):
    setUp=base.SharedFamilyTest.setUp
    tearDown=base.SharedFamilyTest.tearDown
    caregiver=base.SharedFamilyTest.caregiver
    confirm_profile=base.SharedFamilyTest.confirm_profile
    payload=base.SharedFamilyTest.payload
    post_record=base.SharedFamilyTest.post_record
    menu_payload=base.SharedFamilyTest.menu_payload

    def extraction(self,**changes):
        return {'intent':'actual_record','day':DAY,'meal':'午餐','items':[{'food':'米饭','amount':'半碗','acceptance':'吃了','evidence':'吃了半碗米饭'},{'food':'牛肉','amount':'未说明','acceptance':'没吃','evidence':'牛肉没吃'}],'note':'','questions':[],**changes}

    def extract(self,output=None,key=None,text='午饭吃了半碗米饭，牛肉没吃'):
        with provider(json.dumps(output or self.extraction(),ensure_ascii=False)):
            return self.owner.post('/api/record-proposals',json={'text':text},headers={'Idempotency-Key':key or secrets.token_hex(12)})

    def menu(self):
        return {'meals':[{'day':DAY,'meal':'午餐','title':'蔬菜软饭','ingredients':[{'name':'大米','quantity':'20','unit':'克'},{'name':'青菜','quantity':None,'unit':'适量'}],'method':'食材充分处理，煮至适合宝宝咀嚼的质地。','note':'采购量待家长核实'}],'rationale':'根据现有食材生成，待家长确认。'}

    def generate(self,output=None,key=None):
        with provider(json.dumps(output or self.menu(),ensure_ascii=False)):
            return self.owner.post('/api/menu-proposals',json={'start':DAY,'days':1,'meals':['午餐']},headers={'Idempotency-Key':key or secrets.token_hex(12)})

    def confirm(self,proposal,client=None,**changes):
        return (client or self.owner).post('/api/proposals/'+proposal['id']+'/confirm',json={'version':proposal['version'],'review_confirmed':True,**changes})

    def test_record_extraction_is_preview_only_then_explicitly_saved_once(self):
        grandma,_,_=self.caregiver()
        result=self.extract()
        self.assertEqual(result.status_code,200,result.text)
        proposal=result.json()['proposal']
        self.assertEqual(self.owner.get('/api/records').json(),[])
        self.assertEqual(self.confirm(proposal,review_confirmed=False).status_code,422)
        saved=self.confirm(proposal)
        self.assertEqual(saved.status_code,200,saved.text)
        self.assertEqual(self.confirm(proposal).json(),saved.json())
        records=grandma.get('/api/records').json()
        self.assertEqual(len(records),1)
        self.assertEqual(records[0]['items'][0]['amount'],'半碗')
        self.assertEqual(records[0]['items'][1]['acceptance'],'没吃')

    def test_future_plans_never_create_actual_record(self):
        with provider(json.dumps(self.extraction())) as calls:
            r=self.owner.post('/api/record-proposals',json={'text':'明天打算给宝宝吃米饭'})
        self.assertEqual(r.status_code,200)
        self.assertIsNone(r.json()['proposal'])
        self.assertEqual(calls,[])
        self.assertEqual(self.owner.get('/api/records').json(),[])

    def test_missing_meal_requests_clarification(self):
        r=self.extract(self.extraction(meal=None,questions=['这是哪一餐？']))
        self.assertEqual(r.status_code,200)
        self.assertIsNone(r.json()['proposal'])
        self.assertEqual(r.json()['questions'],['这是哪一餐？'])

    def test_invented_food_is_rejected(self):
        result=self.extraction()
        result['items'][0]['food']='菠菜'
        r=self.extract(result)
        self.assertEqual(r.status_code,502)
        self.assertEqual(self.owner.get('/api/proposals').json(),[])

    def test_provider_invalid_json_and_failure_do_not_write_business_data(self):
        for output,fail in [('invalid JSON',False),('unused',True)]:
            with provider(output,fail=fail):
                r=self.owner.post('/api/record-proposals',json={'text':'午饭吃了半碗米饭'},headers={'Idempotency-Key':secrets.token_hex(12)})
            self.assertEqual(r.status_code,502,r.text)
        self.assertEqual(self.owner.get('/api/records').json(),[])
        self.assertEqual(self.owner.get('/api/ai-usage').json()['calls'],2)

    def test_same_generation_key_has_no_second_provider_charge(self):
        with provider(json.dumps(self.extraction(),ensure_ascii=False)) as calls:
            responses=[self.owner.post('/api/record-proposals',json={'text':'午饭吃了半碗米饭，牛肉没吃'},headers={'Idempotency-Key':'same-extract'}) for _ in range(2)]
        self.assertEqual(responses[0].status_code,200,responses[0].text)
        self.assertEqual(responses[0].json()['proposal']['id'],responses[1].json()['proposal']['id'])
        self.assertEqual(len(calls),1)
        self.assertEqual(self.owner.get('/api/ai-usage').json()['calls'],1)

    def test_draft_is_personal_and_duplicate_meal_needs_confirmation(self):
        p=self.extract().json()['proposal']
        grandma,_,_=self.caregiver()
        self.assertEqual(self.confirm(p,client=grandma).status_code,404)
        self.assertEqual(grandma.get('/api/proposals').json(),[])
        self.post_record()
        self.assertEqual(self.confirm(p).status_code,409)
        self.assertEqual(self.confirm(p,confirm_duplicate=True).status_code,200)
        self.assertEqual(len(self.owner.get('/api/records').json()),2)

    def test_record_draft_correction_and_version(self):
        p=self.extract().json()['proposal']
        corrected=p['payload'];corrected['items'][0]['amount']='三口'
        r=self.owner.put('/api/proposals/'+p['id'],json={'version':1,'payload':corrected})
        self.assertEqual(r.status_code,200,r.text)
        self.assertEqual(self.confirm(p).status_code,409)
        self.assertEqual(self.confirm(r.json()).status_code,200)
        self.assertEqual(self.owner.get('/api/records').json()[0]['items'][0]['amount'],'三口')

    def test_week_menu_draft_publish_and_shopping(self):
        self.confirm_profile()
        r=self.generate()
        self.assertEqual(r.status_code,200,r.text)
        self.assertEqual(self.owner.get(f'/api/menus?start={DAY}&end={DAY}').json(),[])
        self.assertEqual(self.confirm(r.json()).status_code,200)
        menu=self.owner.get(f'/api/menus?start={DAY}&end={DAY}').json()[0]
        self.assertEqual(menu['title'],'蔬菜软饭')
        shopping=self.owner.get(f'/api/shopping?start={DAY}&end={DAY}').json()['items']
        by_name={i['name']:i for i in shopping}
        self.assertEqual(Decimal(by_name['大米']['quantity']),20)
        self.assertIsNone(by_name['青菜']['quantity'])
        self.assertEqual(by_name['青菜']['unknown_count'],1)

    def test_menu_cannot_overwrite_intervening_edit_and_publish_is_atomic(self):
        self.confirm_profile()
        p=self.generate().json()
        self.assertEqual(self.owner.put('/api/menus',json=self.menu_payload(),headers={'Idempotency-Key':'intervening'}).status_code,200)
        self.assertEqual(self.confirm(p).status_code,409)
        self.assertEqual(self.owner.get(f'/api/menus?start={DAY}&end={DAY}').json()[0]['title'],'时蔬软饭')

    def test_profile_change_invalidates_menu_draft(self):
        self.confirm_profile()
        p=self.generate().json()
        self.confirm_profile(dislikes='青菜')
        self.assertEqual(self.confirm(p).status_code,409)

    def test_menu_generation_age_scope_is_checked_before_provider(self):
        self.confirm_profile(age_months=8)
        with provider(json.dumps(self.menu())) as calls:
            r=self.owner.post('/api/menu-proposals',json={'start':DAY,'days':1,'meals':['午餐']})
        self.assertEqual(r.status_code,409)
        self.assertEqual(calls,[])

    def test_multi_meal_publish_conflict_leaves_all_other_slots_untouched(self):
        self.confirm_profile()
        payload=self.menu()
        payload['meals'].insert(0,{**payload['meals'][0],'meal':'早餐'})
        with provider(json.dumps(payload,ensure_ascii=False)):
            r=self.owner.post('/api/menu-proposals',json={'start':DAY,'days':1,'meals':['早餐','午餐']})
        self.assertEqual(r.status_code,200,r.text)
        self.owner.put('/api/menus',json=self.menu_payload(),headers={'Idempotency-Key':'other-menu'})
        self.assertEqual(self.confirm(r.json()).status_code,409)
        menus=self.owner.get(f'/api/menus?start={DAY}&end={DAY}').json()
        self.assertEqual([(m['meal'],m['title']) for m in menus],[('午餐','时蔬软饭')])

    def test_menu_rejects_missing_slots_and_allergens(self):
        self.confirm_profile(allergy_status='known',allergies=['花生'])
        payload=self.menu();payload['meals'][0]['ingredients'][0]['name']='花生'
        self.assertEqual(self.generate(payload).status_code,422)
        payload=self.menu();payload['meals'][0]['meal']='早餐'
        self.assertEqual(self.generate(payload).status_code,502)

    def test_generation_permissions_and_unconfirmed_profile(self):
        self.assertEqual(self.generate().status_code,409)
        grandma,_,_=self.caregiver()
        with provider(json.dumps(self.menu())) as calls:
            r=grandma.post('/api/menu-proposals',json={'start':DAY,'days':1})
        self.assertEqual(r.status_code,403)
        self.assertEqual(calls,[])

    def test_daily_limit_is_shared_across_family_members(self):
        self.extract()
        grandma,_,_=self.caregiver()
        with provider(json.dumps(self.extraction())) as calls,patch.dict(os.environ,{'MODEL_DAILY_REQUEST_LIMIT':'1'}):
            r=grandma.post('/api/record-proposals',json={'text':'午饭吃了半碗米饭'})
        self.assertEqual(r.status_code,429)
        self.assertEqual(calls,[])

    def test_invalid_provider_setting_does_not_consume_call_quota(self):
        with provider(json.dumps(self.extraction())) as calls,patch.dict(os.environ,{'MODEL_ENABLE_THINKING':'invalid'}):
            r=self.owner.post('/api/record-proposals',json={'text':'午饭吃了半碗米饭'})
        self.assertEqual(r.status_code,503)
        self.assertEqual(calls,[])
        self.assertEqual(self.owner.get('/api/ai-usage').json()['calls'],0)

    def test_manual_menu_edit_clears_old_purchase_amounts(self):
        self.confirm_profile()
        self.confirm(self.generate().json())
        r=self.owner.put('/api/menus',json=self.menu_payload(version=1,title='手工改为软饭'),headers={'Idempotency-Key':'manual'})
        self.assertEqual(r.status_code,200,r.text)
        shopping=self.owner.get(f'/api/shopping?start={DAY}&end={DAY}').json()['items']
        self.assertTrue(all(i['quantity'] is None for i in shopping))

    def test_expired_proposal_and_migration_reopen(self):
        p=self.extract().json()['proposal']
        with mod.database(True) as db:db.execute('UPDATE proposals SET expires=0 WHERE id=?',(p['id'],))
        self.assertEqual(self.confirm(p).status_code,409)
        self.assertIsNotNone(mod.create_app())
        with mod.database() as db:
            self.assertEqual([r[0] for r in db.execute('SELECT version FROM schema_migrations ORDER BY version')],[1,2])
