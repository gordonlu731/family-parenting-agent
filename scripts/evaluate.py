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


def scrub(value):
    if isinstance(value, dict):
        return {k: scrub(v) for k,v in value.items() if k not in ('id','csrf','token','member_id','family_id','usage_id','item_ids','menu_ids','record_id') and not k.endswith('_id')}
    if isinstance(value, list):
        return [scrub(v) for v in value]
    return value


class ProviderTracker:
    def __init__(self, mock, maximum):
        self.mock, self.maximum = mock, maximum
        self.calls, self.mock_calls, self.injected = 0, 0, 0
        self.case_id, self.fault = '', None

    def factory(self, original):
        tracker = self
        class Client:
            def __init__(self, **kwargs):
                self.actual = original(**kwargs) if not tracker.mock and not tracker.fault else None
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
                elif tracker.mock:
                    tracker.mock_calls += 1
                    content, finish = json.dumps(mock_output(tracker.case_id, kwargs['json']),ensure_ascii=False), 'stop'
                else:
                    if tracker.calls >= tracker.maximum: raise BudgetExhausted()
                    tracker.calls += 1
                    return await self.actual.post(url, **kwargs)
                return httpx.Response(200,request=httpx.Request('POST',url),json={
                    'choices':[{'message':{'content':content},'finish_reason':finish}],
                    'usage':{'prompt_tokens':10,'completion_tokens':10}})
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
    def __init__(self, client, mod, scenario):
        self.client, self.mod, self.scenario = client, mod, scenario
        self.day = datetime.now(mod.TZ).date().isoformat()
        auth = self.post('/bootstrap', {'token':os.environ['BOOTSTRAP_TOKEN'],'family_name':'虚构评测家庭','name':'评测家长'}).json()
        self.owner_id=auth['member_id'];client.headers['X-CSRF-Token']=auth['csrf']
        self.profile()
        self.outputs=[]

    def post(self, path, body, expected=200, key=None):
        result=self.client.post('/api'+path,json=body,headers={'Idempotency-Key':key or secrets.token_hex(12)})
        assert result.status_code==expected, 'unexpected HTTP status at '+path
        return result

    def profile(self, **changes):
        value=self.client.get('/api/profile').json();value.pop('updated_at')
        value.update(age_months=24,allergy_status='none_known');value.update(changes)
        response=self.client.put('/api/profile',json=value)
        assert response.status_code==200

    def record(self, text=None, key=None):
        result=self.post('/record-proposals',{'text':text or self.scenario['input'],'day':self.day},key=key).json()
        self.outputs.append(result)
        assert self.client.get('/api/records').json()==[], 'proposal unexpectedly saved a shared fact'
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
        assert result.status_code==200

    def update_stock(self, name='大米', **changes):
        stock=self.client.get('/api/pantry').json();row=next(i for i in stock['items'] if i['name']==name)
        item={k:row[k] for k in ('id','version','name','quantity','unit','location','kind','status','amount_note')};item.update(changes)
        result=self.client.put('/api/pantry',json={'version':stock['version'],'items':[item],'review_confirmed':True},headers={'Idempotency-Key':secrets.token_hex(12)})
        assert result.status_code==200

    def manual_menu(self, meal='午餐', ingredients=None, day=None):
        day=day or self.day
        menus=self.client.get('/api/menus',params={'start':day,'end':day}).json()
        old=next((i for i in menus if i['meal']==meal),None)
        body={'day':day,'meal':meal,'title':'虚构固定菜单','ingredients':['大米'],'method':'仅为测试用的已核对菜单。','note':'','version':old['version'] if old else 0}
        result=self.client.put('/api/menus',json=body,headers={'Idempotency-Key':secrets.token_hex(12)})
        assert result.status_code==200
        if ingredients:
            with self.mod.database(True) as db:
                for index,(name,quantity,unit) in enumerate(ingredients):
                    db.execute('INSERT INTO menu_ingredients VALUES (?,?,?,?,?)',(result.json()['id'],index,name,quantity,unit))

    def shopping(self):
        result=self.client.get('/api/shopping',params={'start':self.day,'end':self.day}).json()
        self.outputs.append(result)
        return result['items']


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
    assert c.get('/api/menus',params={'start':case.day,'end':case.day}).json()==[]
    assert len(p['payload']['meals'])==(21 if sid=='m02' else 3 if sid in ('m01','m05') else 1)
    if sid=='m05':case.manual_menu();case.confirm(p,409)
    if sid=='m06':case.profile(allergy_status='known',allergies=['花生']);case.confirm(p,409)
    if sid=='p05':assert p['context']['records'] and p['context']['history_menus'] and p['context']['pantry']
    if sid=='p06':case.update_stock(status='used_up');case.confirm(p,409)
    if sid=='p10':
        case.confirm(p);case.shopping();case.update_stock(quantity='80')
        invite=case.post('/invites',{}).json()['path'].split('=',1)[1]
        from fastapi.testclient import TestClient
        with TestClient(c.app,base_url=ORIGIN) as other:
            auth=other.post('/api/join',json={'token':invite,'name':'虚构照顾者'}).json();other.headers['X-CSRF-Token']=auth['csrf']
            result=other.post('/api/records',json={'day':case.day,'meal':'午餐','items':[{'food':'小米粥','amount':'几口','acceptance':'吃了一些'}],'note':'虚构临时换菜'},headers={'Idempotency-Key':'actual-meal'})
            assert result.status_code==200
        assert c.get('/api/review',params={'start':case.day,'end':case.day}).json()['summary']['record_count']==1
        case.manual_menu('晚餐')
        changed=case.menu(replace=True)
        assert changed['context']['records']
        case.confirm(changed)
        assert len(c.get('/api/menus',params={'start':case.day,'end':case.day}).json())==2


def run(scenarios, mock=True, max_calls=5, on_case=None):
    import httpx
    from fastapi.testclient import TestClient
    tracker=ProviderTracker(mock,max_calls)
    results=[]
    original=httpx.AsyncClient
    for scenario in scenarios:
        tracker.case_id=scenario['id'];tracker.fault=None
        before=(tracker.calls,tracker.mock_calls,tracker.injected);started=time.monotonic()
        env={'COOKIE_SECURE':'false','PUBLIC_ORIGIN':ORIGIN,'DEMO_MODE':'false','BOOTSTRAP_TOKEN':secrets.token_urlsafe(48),'MODEL_DAILY_REQUEST_LIMIT':'100'}
        if mock:env.update(MODEL_API_KEY='synthetic-only',MODEL_ID='synthetic-evaluation',MODEL_BASE_URL='https://model.example/v1',MODEL_ENABLE_THINKING='')
        with tempfile.TemporaryDirectory(prefix='family-evaluation-') as tmp:
            env['APP_DB']=str(Path(tmp)/'fictional.sqlite3')
            with patch.dict(os.environ,env),patch('httpx.AsyncClient',tracker.factory(original)):
                mod=importlib.import_module('backend.app')
                with TestClient(mod.create_app(),base_url=ORIGIN) as client:
                    case=Case(client,mod,scenario)
                    status,reason='passed',None
                    try:execute(case,tracker)
                    except BudgetExhausted:status,reason='not_run','provider_call_budget_exhausted'
                    except AssertionError:status,reason='failed','machine_acceptance_assertion_failed'
                    except Exception:status,reason='failed','evaluation_error'
                    usage=client.get('/api/ai-usage').json()
                    results.append({'id':scenario['id'],'kind':scenario['kind'],'machine_status':status,'reason':reason,
                                    'human_review':'pending' if scenario['kind'] not in ('failure','shopping') else 'not_applicable',
                                    'provider_calls':tracker.calls-before[0],'synthetic_calls':tracker.mock_calls-before[1],
                                    'fault_injections':tracker.injected-before[2],'duration_ms':round((time.monotonic()-started)*1000),
                                    'usage':scrub(usage),'outputs':scrub(case.outputs)})
                    if on_case:on_case(results,tracker.calls,tracker.mock_calls)
    return {'format':'family-evaluation-v1','mode':'mock_model' if mock else 'live_model','created_at':datetime.now(timezone.utc).isoformat(),
            'timezone':'Asia/Shanghai','model': 'synthetic-evaluation' if mock else os.getenv('MODEL_ID'),
            'provider_host':'model.example' if mock else urlsplit(os.getenv('MODEL_BASE_URL','')).hostname,
            'provider_calls':tracker.calls,'synthetic_calls':tracker.mock_calls,'max_provider_calls':max_calls,
            'quality_certified':False,'cases':results}


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
    if not args.call_model and not args.mock_model:
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
        def progress(results,calls,mocked):
            stream.seek(0)
            json.dump({'format':'family-evaluation-v1','status':'running','quality_certified':False,'provider_calls':calls,'synthetic_calls':mocked,'cases':results},stream,ensure_ascii=False,indent=2)
            stream.truncate();stream.flush();os.fsync(stream.fileno())
        progress([],0,0)
        report=run(scenarios,args.mock_model,args.max_calls,on_case=progress)
        stream.seek(0);json.dump(report,stream,ensure_ascii=False,indent=2);stream.truncate();stream.flush();os.fsync(stream.fileno())
    passed=sum(c['machine_status']=='passed' for c in report['cases'])
    print(json.dumps({'mode':report['mode'],'machine_passed':passed,'total':len(report['cases']),'provider_calls':report['provider_calls'],'human_review':'pending','quality_certified':False},ensure_ascii=False))
    return 0 if passed==len(report['cases']) else 1


if __name__=='__main__':
    raise SystemExit(main())
