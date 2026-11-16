"""Run fictional acceptance scenarios in isolated databases.

Default: describe the selected cases, with no provider calls or database access.
--mock-model tests the evaluator only. --call-model explicitly permits billable
calls, bounded by --max-calls. Machine checks never certify meal quality.
"""
import argparse
from datetime import date, datetime, timedelta, timezone
import importlib
import json
import os
from pathlib import Path
import re
import secrets
import sys
import tempfile
import time
from unittest.mock import patch
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
ORIGIN = 'http://evaluation.test'


class BudgetExhausted(RuntimeError):
    pass


class MachineCheckError(AssertionError):
    def __init__(self, code):
        self.code = code


class ReplayError(RuntimeError):
    def __init__(self, code):
        self.code = code


def operation(body):
    data = json.loads(body['messages'][1]['content'])
    if 'request' in data:
        req = data['request']
        return ('replacement' if req.get('replace') else 'menu'), req['start']
    if body['messages'][0]['content'].startswith('只整理家里'):
        return 'pantry', None
    return 'record', data.get('today')


def replay_body(entry, start, rebase):
    body = json.loads(json.dumps(entry['body']))
    anchor = entry.get('request_start')
    if rebase and start and anchor and start != anchor:
        content = json.loads(body['choices'][0]['message']['content'])
        shift = date.fromisoformat(start) - date.fromisoformat(anchor)
        for meal in content.get('meals', []):
            meal['day'] = (date.fromisoformat(meal['day']) + shift).isoformat()
        if isinstance(content.get('day'),str):
            content['day'] = (date.fromisoformat(content['day']) + shift).isoformat()
        body['choices'][0]['message']['content'] = json.dumps(content, ensure_ascii=False)
    return body


def load_replay(path):
    path = Path(path)
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError('Replay source must not be a symlink')
    info = path.stat()
    if not path.is_file() or info.st_uid != os.geteuid() or info.st_mode & 0o077 or info.st_size > 4*1024*1024:
        raise ValueError('Replay source must be an owned private file no larger than 4 MiB')
    report = json.loads(path.read_text())
    entries = report.get('provider_replies') if isinstance(report, dict) else None
    if not isinstance(entries, list) or len(entries) > 100:
        raise ValueError('No captured replies; an old report cannot reconstruct an unsaved response')
    for item in entries:
        if (not isinstance(item, dict) or not re.fullmatch(r'[a-z][0-9]{2}', str(item.get('case_id', '')))
                or item.get('operation') not in ('menu', 'replacement', 'record', 'pantry')
                or type(item.get('status')) is not int or not 100 <= item['status'] <= 599
                or not isinstance(item.get('body'), dict)):
            raise ValueError('Invalid captured reply')
        if item.get('request_start') is not None:
            date.fromisoformat(item['request_start'])
    return entries


def scrub(value):
    if isinstance(value, dict):
        return {k: scrub(v) for k,v in value.items() if k not in ('id','csrf','token','member_id','family_id','usage_id','item_ids','menu_ids','record_id') and not k.endswith('_id')}
    if isinstance(value, list):
        return [scrub(v) for v in value]
    return value


class ProviderTracker:
    def __init__(self, mock, maximum, replies=None, capture=False, rebase=False):
        self.mock, self.maximum = mock, maximum
        self.calls, self.mock_calls, self.injected = 0, 0, 0
        self.case_id, self.fault = '', None
        self.replies, self.capture, self.rebase = replies, capture, rebase
        self.replay_calls, self.captured, self.consumed = 0, [], set()
        self.on_reply = None

    def remember(self, response, body):
        if not self.capture or self.fault:
            return response
        kind, start = operation(body)
        # Capture only completion content/finish and numeric usage. Never retain
        # request prompts, auth/response headers or provider error response bodies.
        result = {}
        if response.status_code == 200:
            try:
                raw = response.json()
                result = {'choices':[{'message':{'content':c.get('message',{}).get('content')},
                                      'finish_reason':c.get('finish_reason')}
                                     for c in raw.get('choices',[])],
                          'usage':{k:v for k,v in (raw.get('usage') or {}).items()
                                   if type(v) is int and v >= 0}}
            except (ValueError, TypeError, AttributeError):
                result = {}
        self.captured.append({'case_id':self.case_id, 'operation':kind, 'request_start':start,
                              'captured_mode':'offline_replay' if self.replies is not None else 'mock_model' if self.mock else 'live_model',
                              'status':response.status_code, 'body':result})
        if self.on_reply:
            self.on_reply(self.captured, self.calls, self.mock_calls, self.replay_calls)
        return response

    def factory(self, original):
        tracker = self
        class Client:
            def __init__(self, **kwargs):
                self.actual = original(**kwargs) if not tracker.mock and not tracker.fault and tracker.replies is None else None
            async def __aenter__(self):
                if self.actual: await self.actual.__aenter__()
                return self
            async def __aexit__(self, *args):
                if self.actual: await self.actual.__aexit__(*args)
            async def post(self, url, **kwargs):
                import httpx
                if tracker.fault:
                    tracker.injected += 1
                    fault = tracker.fault
                    if fault == 'timeout': raise httpx.ReadTimeout('synthetic failure')
                    if fault in ('401','429'):
                        return httpx.Response(int(fault), request=httpx.Request('POST',url), text='SYNTHETIC_PRIVATE_BODY')
                    content, finish = ('invalid JSON','stop') if fault=='json' else ('{}','length')
                elif tracker.replies is not None:
                    pending=[(i,v) for i,v in enumerate(tracker.replies)
                             if v['case_id']==tracker.case_id and i not in tracker.consumed]
                    if not pending: raise ReplayError('replay_reply_missing')
                    index, entry = pending[0]
                    kind, start = operation(kwargs['json'])
                    if entry['operation'] != kind: raise ReplayError('replay_operation_mismatch')
                    if not tracker.rebase and start != entry.get('request_start'):
                        raise ReplayError('replay_date_mismatch')
                    if tracker.rebase and start != entry.get('request_start') and (not start or not entry.get('request_start')):
                        raise ReplayError('replay_date_anchor_missing')
                    try: body = replay_body(entry, start, tracker.rebase)
                    except (ValueError, KeyError, TypeError, IndexError): raise ReplayError('replay_date_rebase_failed') from None
                    tracker.consumed.add(index);tracker.replay_calls += 1
                    response=httpx.Response(entry['status'],request=httpx.Request('POST',url),json=body)
                    return tracker.remember(response,kwargs['json'])
                elif tracker.mock:
                    tracker.mock_calls += 1
                    content, finish = json.dumps(mock_output(tracker.case_id, kwargs['json']),ensure_ascii=False), 'stop'
                else:
                    if tracker.calls >= tracker.maximum: raise BudgetExhausted()
                    tracker.calls += 1
                    response = await self.actual.post(url, **kwargs)
                    return tracker.remember(response,kwargs['json'])
                response = httpx.Response(200,request=httpx.Request('POST',url),json={
                    'choices':[{'message':{'content':content},'finish_reason':finish}],
                    'usage':{'prompt_tokens':10,'completion_tokens':10}})
                return tracker.remember(response,kwargs['json'])
        return Client


def mock_output(case_id, body):
    """Canned provider replies validate this runner, not language-model accuracy."""
    data = json.loads(body['messages'][1]['content'])
    if 'request' in data:
        req = data['request']; start = date.fromisoformat(req['start'])
        refs = [v['ref'] for v in data['family_context']['pantry'][:1]]
        return {'meals':[{'day':(start+timedelta(days=i)).isoformat(),'meal':meal,
                         'title':('QA替换' if req.get('replace') else 'QA')+meal,
                         'ingredients':[{'name':'花生' if case_id=='m03' else '大米','quantity':'20','unit':'克'}],
                         'method':'虚构做法：食材充分处理并煮熟。','note':''}
                        for i in range(req['days']) for meal in req['meals']],
                'rationale':'合成回复，仅用于验证评测工具。','basis':refs}
    text = data['text']; day = datetime.now(ZoneInfo('Asia/Shanghai')).date()
    if body['messages'][0]['content'].startswith('只整理家里'):
        items = [{'name':'番茄','quantity':'2','unit':'个','amount_note':'','location':'冷藏' if case_id=='p01' else '未说明',
                  'kind':'raw','status':'used_up' if case_id=='p03' else 'available',
                  'evidence':'冷藏还有2个番茄' if case_id=='p01' else text}]
        if case_id=='p01': items.append({'name':'牛肉','quantity':None,'unit':'适量','amount_note':'','location':'未说明','kind':'raw','status':'used_up','evidence':'牛肉用完了'})
        return {'intent':'actual_inventory','items':items,'questions':[]}
    if case_id=='r03': return {'intent':'unclear','day':day.isoformat(),'meal':None,'items':[],'note':'','questions':['这是哪一餐？']}
    food, amount, acceptance, meal = '米饭','三口' if '三口' in text else '半碗','吃了','午餐'
    if case_id=='r01':
        items=[{'food':'米饭','amount':'半碗','acceptance':'吃了','evidence':'半碗米饭'},{'food':'牛肉','amount':'未说明','acceptance':'没吃','evidence':'牛肉没吃'}]
    else:
        if case_id=='r02': day-=timedelta(days=1);food,amount,meal='粥','几口','晚餐'
        if case_id=='r06': food,amount,acceptance='鸡蛋','未说明','没吃'
        if case_id=='r07': food,amount='青菜','未说明'
        if case_id=='r08': food,amount,meal='奶','半杯','早餐'
        if case_id=='r10': food,amount,acceptance='土豆','未说明','没吃'
        items=[{'food':food,'amount':amount,'acceptance':acceptance,'evidence':food}]
    return {'intent':'actual_record','day':day.isoformat(),'meal':meal,'items':items,'note':'','questions':[]}


class Case:
    def __init__(self, client, mod, scenario, setup=True):
        self.client, self.mod, self.scenario = client, mod, scenario
        self.day = datetime.now(mod.TZ).date().isoformat()
        self.outputs, self.trace = [], []
        self.last_step = 'setup'
        if setup: self.initialize()

    def check(self, condition, code, **facts):
        self.last_step = code
        # Diagnostic values are only counts/statuses/booleans supplied by this
        # runner, never response bodies, tokens, user input or exception text.
        details = {k:v for k,v in facts.items() if type(v) in (int,bool) or v is None}
        self.trace.append({'step':code, 'passed':bool(condition), **details})
        if not condition: raise MachineCheckError(code)

    def initialize(self):
        auth = self.post('/bootstrap', {'token':os.environ['BOOTSTRAP_TOKEN'],'family_name':'虚构评测家庭','name':'评测家长'}).json()
        self.owner_id=auth['member_id'];self.client.headers['X-CSRF-Token']=auth['csrf']
        self.profile()

    def post(self, path, body, expected=200, key=None):
        code='proposal_confirm' if path.startswith('/proposals/') else path.strip('/').replace('-','_')
        self.last_step='request.'+code
        result=self.client.post('/api'+path,json=body,headers={'Idempotency-Key':key or secrets.token_hex(12)})
        self.check(result.status_code==expected,'http.'+code,expected=expected,actual=result.status_code)
        return result

    def profile(self, **changes):
        value=self.client.get('/api/profile').json();value.pop('updated_at')
        value.update(age_months=24,allergy_status='none_known');value.update(changes)
        response=self.client.put('/api/profile',json=value)
        self.check(response.status_code==200,'http.profile',expected=200,actual=response.status_code)

    def record(self, text=None, key=None):
        result=self.post('/record-proposals',{'text':text or self.scenario['input'],'day':self.day},key=key).json()
        self.outputs.append(result)
        rows = self.client.get('/api/records').json()
        self.check(rows==[], 'record.draft_did_not_write',actual=len(rows),expected=0)
        return result

    def menu(self, days=1, meals=None, **changes):
        result=self.post('/menu-proposals',{'start':self.day,'days':days,'meals':meals or ['午餐'],'instructions':self.scenario['input'],**changes}).json()
        self.outputs.append(result)
        return result

    def confirm(self, p, expected=200):
        return self.post('/proposals/'+p['id']+'/confirm',{'version':p['version'],'review_confirmed':True},expected).json()

    def stock(self, name='大米', quantity='30', unit='克', location='常温', kind='raw', status='available'):
        version=self.client.get('/api/pantry').json()['version']
        item={'version':0,'name':name,'quantity':quantity,'unit':unit,'location':location,'kind':kind,'status':status,'amount_note':''}
        result=self.client.put('/api/pantry',json={'version':version,'items':[item],'review_confirmed':True},headers={'Idempotency-Key':secrets.token_hex(12)})
        self.check(result.status_code==200,'http.pantry_create',expected=200,actual=result.status_code)

    def update_stock(self, name='大米', client=None, **changes):
        client = client or self.client
        stock=client.get('/api/pantry').json();row=next(i for i in stock['items'] if i['name']==name)
        item={k:row[k] for k in ('id','version','name','quantity','unit','location','kind','status','amount_note')};item.update(changes)
        result=client.put('/api/pantry',json={'version':stock['version'],'items':[item],'review_confirmed':True},headers={'Idempotency-Key':secrets.token_hex(12)})
        self.check(result.status_code==200,'http.pantry_update',expected=200,actual=result.status_code)

    def manual_menu(self, meal='午餐', ingredients=None, day=None):
        day=day or self.day
        menus=self.client.get('/api/menus',params={'start':day,'end':day}).json()
        old=next((i for i in menus if i['meal']==meal),None)
        body={'day':day,'meal':meal,'title':'虚构固定菜单','ingredients':['大米'],'method':'仅为测试用的已核对菜单。','note':'','version':old['version'] if old else 0}
        result=self.client.put('/api/menus',json=body,headers={'Idempotency-Key':secrets.token_hex(12)})
        self.check(result.status_code==200,'http.manual_menu',expected=200,actual=result.status_code)
        if ingredients:
            with self.mod.database(True) as db:
                for index,(name,quantity,unit) in enumerate(ingredients):
                    db.execute('INSERT INTO menu_ingredients VALUES (?,?,?,?,?)',(result.json()['id'],index,name,quantity,unit))

    def shopping(self):
        response=self.client.get('/api/shopping',params={'start':self.day,'end':self.day})
        self.check(response.status_code==200,'http.shopping',expected=200,actual=response.status_code)
        result=response.json()
        self.outputs.append(result)
        return result['items']


def execute_flow(case, proposal):
    """One canonical two-caregiver flow for mock, captured replay and live checks."""
    from fastapi.testclient import TestClient
    c=case.client;dates={'start':case.day,'end':case.day}
    stock_before=c.get('/api/pantry').json()
    case.confirm(proposal)
    case.shopping()
    case.check(c.get('/api/pantry').json()==stock_before,'flow.publish_and_shopping_preserve_stock')
    invite=case.post('/invites',{}).json()['path'].split('=',1)[1]
    with TestClient(c.app,base_url=ORIGIN) as other:
        joined=other.post('/api/join',json={'token':invite,'name':'虚构照顾者'})
        case.check(joined.status_code==200,'flow.caregiver_join',expected=200,actual=joined.status_code)
        auth=joined.json();other.headers['X-CSRF-Token']=auth['csrf']
        case.check(other.get('/api/menus',params=dates).json()==c.get('/api/menus',params=dates).json(),
                   'flow.shared_plan_visible')
        case.update_stock(quantity='80',client=other)
        case.check(other.get('/api/pantry').json()==c.get('/api/pantry').json(),'flow.shared_stock_updated')
        result=other.post('/api/records',json={'day':case.day,'meal':'午餐',
            'items':[{'food':'小米粥','amount':'几口','acceptance':'吃了一些'}],'note':'虚构临时换菜'},
            headers={'Idempotency-Key':'actual-meal'})
        case.check(result.status_code==200,'flow.caregiver_actual_record',expected=200,actual=result.status_code)
        records=c.get('/api/records').json()
        case.check(len(records)==1 and records[0]['member_id']==auth['member_id'],
                   'flow.actual_actor_preserved',expected=1,actual=len(records))
        review=c.get('/api/review',params=dates).json()
        case.check(review['summary']['record_count']==1,'flow.actual_visible_in_review',
                   expected=1,actual=review['summary']['record_count'])
        case.manual_menu('晚餐')
        menus=c.get('/api/menus',params=dates).json()
        dinner=next(i for i in menus if i['meal']=='晚餐')
        stock=c.get('/api/pantry').json()
        changed=case.menu(replace=True)
        case.check(bool(changed['context']['records']),'flow.replacement_uses_actual_context')
        case.check(other.get('/api/proposals').json()==[],'flow.replacement_draft_is_private')
        case.check(c.get('/api/menus',params=dates).json()==menus,'flow.replacement_draft_did_not_publish')
        case.confirm(changed)
        final=c.get('/api/menus',params=dates).json()
        case.check(len(final)==2,'flow.replacement_retains_two_slots',expected=2,actual=len(final))
        case.check(next(i for i in final if i['meal']=='晚餐')==dinner,'flow.replacement_preserves_other_meal')
        planned=changed['payload']['meals'][0]
        lunch=next(i for i in final if i['meal']=='午餐')
        case.check(lunch['title']==planned['title'],'flow.reviewed_replacement_saved')
        case.check(c.get('/api/records').json()==records,'flow.replacement_preserves_actual_record')
        case.check(c.get('/api/pantry').json()==stock,'flow.replacement_preserves_stock')
        case.shopping()
        case.check(c.get('/api/pantry').json()==stock,'flow.final_shopping_is_read_only')
        case.check(other.get('/api/menus',params=dates).json()==final,'flow.final_shared_plan_visible')


def execute(case, tracker):
    sid=case.scenario['id'];c=case.client
    if sid.startswith('r'):
        if sid in ('r11','r12'):
            result=case.record('今天午饭吃了半碗米饭',key='stable-record-key')
        else: result=case.record()
        p=result.get('proposal')
        if sid in ('r03','r04','r05'):
            assert p is None and result['questions'];return
        if sid=='r09': return
        assert p and p['kind']=='record'
        items=p['payload']['items']
        if sid=='r01':
            assert any(i['food']=='米饭' and i['amount']=='半碗' for i in items)
            assert any(i['food']=='牛肉' and i['acceptance']=='没吃' for i in items)
        if sid=='r02': assert p['payload']['day']==(date.fromisoformat(case.day)-timedelta(days=1)).isoformat() and p['payload']['meal']=='晚餐' and any(i['amount']=='几口' for i in items)
        if sid in ('r06','r10'): assert items and all(i['acceptance']=='没吃' for i in items)
        if sid=='r07': assert all(i['amount']=='未说明' for i in items)
        if sid=='r08':
            case.confirm(p)
            assert c.get('/api/records').json()[0]['member_id']==case.owner_id
        if sid=='r11':
            again=case.record('今天午饭吃了半碗米饭',key='stable-record-key')['proposal']
            assert again['id']==p['id']
            case.confirm(p);case.confirm(p)
            assert len(c.get('/api/records').json())==1
        if sid=='r12':
            payload=p['payload'];payload['items'][0]['amount']='三口'
            assert c.put('/api/proposals/'+p['id'],json={'version':p['version'],'payload':payload}).status_code==200
            case.confirm(p,409)
        return
    if sid=='f01':
        for fault in ('timeout','401','429','json','truncated'):
            tracker.fault=fault
            result=c.post('/api/record-proposals',json={'text':'今天午饭吃了半碗米饭'},headers={'Idempotency-Key':secrets.token_hex(12)})
            assert result.status_code==502 and 'SYNTHETIC_PRIVATE_BODY' not in result.text
            assert c.get('/api/records').json()==[]
        tracker.fault=None;return
    if sid in ('s01','p07','p08','p09'):
        if sid=='s01':
            case.manual_menu(ingredients=[('大米','20','克'),('大米','1','个'),('青菜',None,'适量')])
            case.manual_menu('晚餐',ingredients=[('大米','20','克')])
            rows=case.shopping();assert len(rows)==3 and next(i for i in rows if i['name']=='大米' and i['unit']=='克')['quantity']=='4E+1'
        if sid=='p07':
            case.stock();case.manual_menu(ingredients=[('大米','40','克')])
            assert case.shopping()[0]['buy_quantity']=='1E+1'
        if sid=='p08':
            case.stock(quantity=None,unit='适量');case.manual_menu(ingredients=[('大米','20','克')])
            assert case.shopping()[0]['category']=='check'
        if sid=='p09':
            case.stock(kind='cooked');case.stock('青菜','20','克')
            with case.mod.database(True) as db:db.execute('UPDATE pantry SET confirmed_at=? WHERE name=?',((datetime.now(case.mod.TZ)-timedelta(days=8)).isoformat(),'青菜'))
            case.manual_menu(ingredients=[('大米','20','克'),('青菜','20','克')])
            rows={i['name']:i for i in case.shopping()};assert rows['大米']['category']=='need_buy' and rows['青菜']['category']=='check'
        return
    if sid in ('p01','p02','p03','p04'):
        text=case.scenario['input']
        if sid=='p03':
            case.stock('番茄','2','个','冷藏');case.stock('番茄','2','个','冷冻');text='番茄用完了。'
        before=c.get('/api/pantry').json()
        result=case.post('/pantry-proposals',{'text':text}).json();case.outputs.append(result)
        assert c.get('/api/pantry').json()==before
        if sid in ('p02','p03'): assert result['proposal'] is None and result['questions'];return
        p=result['proposal'];assert p and p['kind']=='pantry'
        if sid=='p01':
            case.confirm(p)
            rows={i['name']:i for i in c.get('/api/pantry').json()['items']}
            assert rows['番茄']['quantity']=='2' and rows['牛肉']['status']=='used_up' and rows['牛肉']['quantity'] is None
        else:
            assert all(i['quantity'] is None or (i['unit']=='个' and i['quantity']=='2') for i in p['payload']['items'])
        return
    if sid=='m04':
        case.profile(allergy_status='unknown')
        case.post('/menu-proposals',{'start':case.day,'days':1},409);return
    if sid=='m03':
        case.profile(allergy_status='known',allergies=['花生'])
        result=c.post('/api/menu-proposals',json={'start':case.day,'days':1,'meals':['午餐'],'instructions':case.scenario['input']},headers={'Idempotency-Key':secrets.token_hex(12)})
        assert result.status_code in (200,422)
        if result.status_code==200:
            case.outputs.append(result.json())
            assert all('花生' not in json.dumps(i,ensure_ascii=False) for i in result.json()['payload']['meals'])
        return
    case.stock()
    if sid=='p05':
        yesterday=(date.fromisoformat(case.day)-timedelta(days=1)).isoformat()
        case.manual_menu(day=yesterday)
        case.post('/records',{'day':yesterday,'meal':'午餐','items':[{'food':'南瓜','amount':'未说明','acceptance':'没吃'}],'note':'虚构反馈'})
    p=case.menu(days=7 if sid=='m02' else 1,meals=['早餐','午餐','晚餐'] if sid in ('m01','m02','m05') else ['午餐'])
    case.check(c.get('/api/menus',params={'start':case.day,'end':case.day}).json()==[],
               'menu.draft_did_not_publish')
    expected=21 if sid=='m02' else 3 if sid in ('m01','m05') else 1
    case.check(len(p['payload']['meals'])==expected,'menu.expected_slot_count',
               expected=expected,actual=len(p['payload']['meals']))
    if sid=='m05':case.manual_menu();case.confirm(p,409)
    if sid=='m06':case.profile(allergy_status='known',allergies=['花生']);case.confirm(p,409)
    if sid=='p05':assert p['context']['records'] and p['context']['history_menus'] and p['context']['pantry']
    if sid=='p06':case.update_stock(status='used_up');case.confirm(p,409)
    if sid=='p10':
        execute_flow(case,p)


def failure_location(exc):
    cursor=exc.__traceback__;location=None
    while cursor:
        path=Path(cursor.tb_frame.f_code.co_filename).resolve()
        if path.is_relative_to(ROOT):
            location={'source':str(path.relative_to(ROOT)), 'line':cursor.tb_lineno,
                      'function':cursor.tb_frame.f_code.co_name}
        cursor=cursor.tb_next
    return location


def run(scenarios, mock=True, max_calls=5, on_case=None, replay=None, capture=False,
        rebase=False, on_capture=None):
    import httpx
    from fastapi.testclient import TestClient
    tracker=ProviderTracker(mock if replay is None else False,max_calls,replay,capture,rebase)
    tracker.on_reply=on_capture
    mode='offline_replay' if replay is not None else 'mock_model' if mock else 'live_model'
    results=[]
    original=httpx.AsyncClient
    for scenario in scenarios:
        tracker.case_id=scenario['id'];tracker.fault=None
        before=(tracker.calls,tracker.mock_calls,tracker.injected,tracker.replay_calls);started=time.monotonic()
        env={'COOKIE_SECURE':'false','PUBLIC_ORIGIN':ORIGIN,'DEMO_MODE':'false','BOOTSTRAP_TOKEN':secrets.token_urlsafe(48),'MODEL_DAILY_REQUEST_LIMIT':'100'}
        if mock or replay is not None:
            env.update(MODEL_API_KEY='synthetic-only',MODEL_ID='synthetic-evaluation',MODEL_BASE_URL='https://model.example/v1',MODEL_ENABLE_THINKING='')
        with tempfile.TemporaryDirectory(prefix='family-evaluation-') as tmp:
            env['APP_DB']=str(Path(tmp)/'fictional.sqlite3')
            with patch.dict(os.environ,env),patch('httpx.AsyncClient',tracker.factory(original)):
                mod=importlib.import_module('backend.app')
                with TestClient(mod.create_app(),base_url=ORIGIN) as client:
                    case=Case(client,mod,scenario,setup=False)
                    status,reason,location='passed',None,None
                    failure_step=None
                    try:
                        case.initialize()
                        execute(case,tracker)
                        if replay is not None and any(v['case_id']==scenario['id'] and i not in tracker.consumed
                                                      for i,v in enumerate(replay)):
                            raise ReplayError('replay_replies_unused')
                    except BudgetExhausted:
                        status,reason='not_run','provider_call_budget_exhausted'
                    except ReplayError as exc:
                        status,reason,location='failed',exc.code,failure_location(exc)
                        failure_step=case.last_step
                    except AssertionError as exc:
                        status,reason,location='failed','machine_acceptance_assertion_failed',failure_location(exc)
                        failure_step=exc.code if isinstance(exc,MachineCheckError) else case.last_step
                    except Exception as exc:
                        status,reason,location='failed','evaluation_error',failure_location(exc)
                        failure_step=case.last_step
                    try: usage=client.get('/api/ai-usage').json()
                    except Exception: usage={}
                    results.append({'id':scenario['id'],'kind':scenario['kind'],'machine_status':status,'reason':reason,
                                    'failure_step':failure_step,'failure_location':location,'steps':case.trace,
                                    'human_review':'pending' if scenario['kind'] not in ('failure','shopping') else 'not_applicable',
                                    'provider_calls':tracker.calls-before[0],'synthetic_calls':tracker.mock_calls-before[1],
                                    'replay_calls':tracker.replay_calls-before[3],
                                    'fault_injections':tracker.injected-before[2],'duration_ms':round((time.monotonic()-started)*1000),
                                    'usage':scrub(usage),'outputs':scrub(case.outputs)})
                    if on_case:on_case(results,tracker.calls,tracker.mock_calls)
    report={'format':'family-evaluation-v1','mode':mode,'created_at':datetime.now(timezone.utc).isoformat(),
            'timezone':'Asia/Shanghai','model': 'replayed-fixture' if replay is not None else 'synthetic-evaluation' if mock else os.getenv('MODEL_ID'),
            'provider_host':'model.example' if mock or replay is not None else urlsplit(os.getenv('MODEL_BASE_URL','')).hostname,
            'provider_calls':tracker.calls,'synthetic_calls':tracker.mock_calls,'replay_calls':tracker.replay_calls,
            'replay_date_rebasing':bool(replay is not None and rebase),
            'max_provider_calls':0 if replay is not None else max_calls,
            'quality_certified':False,'cases':results}
    if capture: report['provider_replies']=tracker.captured
    return report


def open_report(path):
    path=Path(path)
    if path.resolve().is_relative_to(ROOT) and not path.resolve().is_relative_to(ROOT/'data'):
        raise ValueError('Reports inside the repository must be under ignored data/')
    path.parent.mkdir(parents=True,mode=0o700,exist_ok=True)
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    return os.fdopen(fd,'w')


def write_report(path, report):
    with open_report(path) as stream:json.dump(report,stream,ensure_ascii=False,indent=2)


def model_configured():
    base=os.getenv('MODEL_BASE_URL','')
    try:parsed=urlsplit(base)
    except ValueError:return False
    if any(ch.isspace() for ch in base):return False
    return bool(all(os.getenv(k,'').strip() for k in ('MODEL_API_KEY','MODEL_BASE_URL','MODEL_ID')) and parsed.scheme=='https' and parsed.hostname and not parsed.username and not parsed.password and not parsed.query and not parsed.fragment and not parsed.path.rstrip('/').endswith('/chat/completions') and os.getenv('MODEL_ENABLE_THINKING','').strip().lower() in ('','true','false'))


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    mode=parser.add_mutually_exclusive_group()
    mode.add_argument('--call-model',action='store_true')
    mode.add_argument('--mock-model',action='store_true')
    mode.add_argument('--replay',type=Path,help='offline replay of a private report containing captured replies; never contacts a provider')
    parser.add_argument('--capture-responses',action='store_true',help='save completion-only fictional replies in the private report for later offline replay')
    parser.add_argument('--rebase-replay-dates',action='store_true',help='explicitly shift captured menu dates to the current request date; this is a transformed replay')
    select=parser.add_mutually_exclusive_group()
    select.add_argument('--all',action='store_true')
    select.add_argument('--cases',default=None)
    parser.add_argument('--max-calls',type=int,choices=range(1,31),default=5,metavar='1..30')
    parser.add_argument('--output',type=Path)
    args=parser.parse_args(argv)
    all_cases=json.loads((ROOT/'evals/family-scenarios.json').read_text())
    ids={s['id'] for s in all_cases}
    selected=ids if args.all else set((args.cases or 'r01,r03,m01,p01').split(','))
    if not selected<=ids:parser.error('Unknown scenario IDs')
    scenarios=[s for s in all_cases if s['id'] in selected]
    if args.rebase_replay_dates and args.replay is None:
        parser.error('--rebase-replay-dates requires --replay')
    replay=None
    if args.replay is not None:
        try: replay=load_replay(args.replay)
        except (OSError,ValueError,TypeError):
            parser.error('Could not read private captured replies; old reports cannot recreate unsaved responses. No model calls made.')
    if args.capture_responses and not (args.call_model or args.mock_model or args.replay is not None):
        parser.error('Choose an explicit evaluation mode before capturing responses')
    if not args.call_model and not args.mock_model and args.replay is None:
        configured=model_configured()
        print(json.dumps({'mode':'dry_run','provider_calls':0,'model_configured':configured,'database_opened':False,'cases':[s['id'] for s in scenarios],'note':'Use --call-model only after secure model configuration. Requests may be billable; the call limit is not a currency cap.'},ensure_ascii=False))
        return 0
    if args.call_model:
        if not model_configured():
            parser.error('Configure the model securely with a valid HTTPS base URL before live evaluation')
    report_dir=Path(os.getenv('EVAL_REPORT_DIR') or str(Path(os.getenv('APP_DB',str(ROOT/'data/family.sqlite3'))).parent/'evaluations'))
    output=args.output or report_dir/('evaluation-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+secrets.token_hex(4)+'.json')
    # Refuse unsafe/existing report paths before any potentially billable request.
    if output.exists() or output.is_symlink() or (output.resolve().is_relative_to(ROOT) and not output.resolve().is_relative_to(ROOT/'data')):
        parser.error('Choose a new report path outside tracked source files')
    try:
        stream=open_report(output)
    except (OSError,ValueError):
        parser.error('Could not reserve a private report file; no model calls made')
    with stream:
        captured=[];replayed=0
        def progress(results,calls,mocked):
            stream.seek(0)
            value={'format':'family-evaluation-v1','status':'running','quality_certified':False,
                   'provider_calls':calls,'synthetic_calls':mocked,'replay_calls':replayed,'cases':results}
            if args.capture_responses: value['provider_replies']=captured
            json.dump(value,stream,ensure_ascii=False,indent=2)
            stream.truncate();stream.flush();os.fsync(stream.fileno())
        latest=[]
        def capture_progress(entries,calls,mocked,count):
            nonlocal replayed
            captured[:]=entries;replayed=count
            progress(latest,calls,mocked)
        def case_progress(results,calls,mocked):
            latest[:]=results
            progress(results,calls,mocked)
        progress([],0,0)
        report=run(scenarios,args.mock_model,args.max_calls,on_case=case_progress,replay=replay,
                   capture=args.capture_responses,rebase=args.rebase_replay_dates,on_capture=capture_progress)
        stream.seek(0);json.dump(report,stream,ensure_ascii=False,indent=2);stream.truncate();stream.flush();os.fsync(stream.fileno())
    passed=sum(c['machine_status']=='passed' for c in report['cases'])
    print(json.dumps({'mode':report['mode'],'machine_passed':passed,'total':len(report['cases']),
                      'provider_calls':report['provider_calls'],'replay_calls':report['replay_calls'],
                      'failures':[{'id':c['id'],'step':c['failure_step'],'reason':c['reason']}
                                  for c in report['cases'] if c['machine_status']!='passed'],
                      'human_review':'pending','quality_certified':False},ensure_ascii=False))
    return 0 if passed==len(report['cases']) else 1


if __name__=='__main__':
    raise SystemExit(main())
