"""Exercise the built UI against the real ASGI app and synthetic model replies.

No listening server, production database, real credentials or external model.
Playwright routes same-origin requests into a separate TestClient per browser.
"""
import argparse
import importlib
import json
import os
import re
import secrets
import sys
import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
ORIGIN = 'http://family.test'


class SyntheticProvider:
    def __init__(self, **_):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        pass

    async def post(self, url, **kwargs):
        import httpx
        body = kwargs['json']
        data = json.loads(body['messages'][1]['content'])
        request = data['request']
        start = date.fromisoformat(request['start'])
        replacing = request.get('replace', False)
        meals = [{'day': (start+timedelta(days=i)).isoformat(), 'meal': meal,
                  'title': ('QA替换' if replacing else 'QA')+meal,
                  'ingredients': [{'name': '大米', 'quantity': '20', 'unit': '克'}],
                  'method': '虚构测试做法：食材充分处理并煮熟。', 'note': '仅为页面测试'}
                 for i in range(request['days']) for meal in request['meals']]
        refs = [i['ref'] for i in data['family_context']['pantry'][:1]]
        content = {'meals': meals, 'rationale': '虚构测试建议，非真实模型结果。', 'basis': refs}
        return httpx.Response(200, request=httpx.Request('POST', url), json={
            'choices': [{'message': {'content': json.dumps(content, ensure_ascii=False)}, 'finish_reason': 'stop'}],
            'usage': {'prompt_tokens': 10, 'completion_tokens': 10}})


def route_app(page, client):
    def bridge(route):
        request = route.request
        url = urlsplit(request.url)
        if url.scheme+'://'+url.netloc != ORIGIN:
            route.abort()
            return
        client.cookies.clear()
        headers = {k: v for k, v in request.headers.items() if k not in ('host', 'content-length')}
        # Browser cookies, including an explicitly absent cookie, are authoritative.
        headers['cookie'] = request.headers.get('cookie', '')
        response = client.request(request.method, url.path+('?' + url.query if url.query else ''),
                                  headers=headers, content=request.post_data_buffer)
        outgoing = {k: v for k, v in response.headers.items()
                    if k not in ('content-length', 'content-encoding', 'transfer-encoding')}
        route.fulfill(status=response.status_code, headers=outgoing, body=response.content)
    page.route('**/*', bridge)


def run(output, executable=None):
    from playwright.sync_api import sync_playwright, expect
    from fastapi.testclient import TestClient
    output.mkdir(parents=True, exist_ok=True)
    completed = []
    stage = 'launch'
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, **({'executable_path': executable} if executable else {}))
        try:
            for name, viewport in [('desktop', {'width': 1440, 'height': 1000}), ('mobile', {'width': 390, 'height': 844})]:
                with tempfile.TemporaryDirectory(prefix='family-ui-') as tmp:
                    env = {'APP_DB': str(Path(tmp)/'fictional.sqlite3'), 'COOKIE_SECURE': 'false',
                           'PUBLIC_ORIGIN': ORIGIN, 'DEMO_MODE': 'false', 'BOOTSTRAP_TOKEN': secrets.token_urlsafe(48),
                           'MODEL_API_KEY': 'synthetic-only', 'MODEL_BASE_URL': 'https://model.example/v1',
                           'MODEL_ID': 'synthetic-ui', 'MODEL_DAILY_REQUEST_LIMIT': '30'}
                    with patch.dict(os.environ, env), patch('httpx.AsyncClient', SyntheticProvider):
                        mod = importlib.import_module('backend.app')
                        app = mod.create_app()
                        with TestClient(app, base_url=ORIGIN) as owner, TestClient(app, base_url=ORIGIN) as caregiver:
                            auth = owner.post('/api/bootstrap', json={'token': env['BOOTSTRAP_TOKEN'], 'family_name': '虚构验收家庭', 'name': '测试家长'})
                            assert auth.status_code == 200
                            token = owner.cookies.get('family_session')
                            owner.headers.update({'X-CSRF-Token': auth.json()['csrf'], 'Cookie': 'family_session='+token})
                            profile = owner.get('/api/profile').json()
                            profile.pop('updated_at')
                            profile.update(age_months=24, allergy_status='none_known')
                            assert owner.put('/api/profile', json=profile).status_code == 200
                            context = browser.new_context(viewport=viewport)
                            context.add_cookies([{'name': 'family_session', 'value': token, 'url': ORIGIN}])
                            page = context.new_page()
                            route_app(page, owner)
                            errors = []
                            page.on('pageerror', lambda exc: errors.append(type(exc).__name__))
                            stage = name+':pantry'
                            page.goto(ORIGIN)
                            page.get_by_role('button', name='家里食材', exact=True).click()
                            dialog = page.get_by_role('dialog')
                            dialog.get_by_role('button', name='添加食材', exact=True).click()
                            dialog.get_by_label('食材名称', exact=True).fill('大米')
                            dialog.get_by_label('当前总量（可留空）', exact=True).fill('30')
                            dialog.get_by_label('存放位置', exact=True).select_option('常温')
                            dialog.get_by_label('我已核对，这是家里现在实际的食材情况。').check()
                            dialog.get_by_role('button', name='确认更新，全家可见', exact=True).click()
                            expect(dialog.locator('.pantry-item')).to_have_count(1)
                            page.screenshot(path=str(output/(name+'-pantry.png')))
                            dialog.get_by_role('button', name='关闭', exact=True).click()
                            stage = name+':menu-draft'
                            page.get_by_role('button', name='生成菜单草稿', exact=True).click()
                            dialog = page.get_by_role('dialog')
                            dialog.get_by_label('安排几天', exact=True).select_option('1')
                            dialog.get_by_role('button', name='生成三餐菜单草稿', exact=True).click()
                            expect(page.get_by_role('dialog')).to_have_attribute('aria-label', '核对菜单草稿')
                            expect(dialog.get_by_role('button', name='发布菜单，全家可见', exact=True)).to_be_disabled()
                            dialog.get_by_label('我已核对全部菜品、配料及食材处理方式，同意发布。').check()
                            dialog.get_by_role('button', name='发布菜单，全家可见', exact=True).click()
                            expect(page.get_by_role('dialog')).to_have_count(0)
                            stage = name+':shopping'
                            page.get_by_role('button', name='看七天', exact=True).click()
                            dialog = page.get_by_role('dialog')
                            expect(dialog.get_by_text('预计补买 30 克', exact=True)).to_be_visible()
                            page.screenshot(path=str(output/(name+'-shopping-before.png')))
                            dialog.get_by_role('button', name='买完了 / 核对家里食材', exact=True).click()
                            dialog.get_by_role('button', name='更正 / 确认余量', exact=True).click()
                            dialog.get_by_label('当前总量（可留空）', exact=True).fill('80')
                            dialog.get_by_label('我已核对，这是家里现在实际的食材情况。').check()
                            dialog.get_by_role('button', name='确认更新，全家可见', exact=True).click()
                            expect(dialog.locator('.pantry-item').get_by_text('80 克', exact=True)).to_be_visible()
                            dialog.get_by_role('button', name='关闭', exact=True).click()
                            expect(page.get_by_role('dialog')).to_have_attribute('aria-label', '接下来七天的菜单')
                            expect(dialog.get_by_text('家里已有足够记录', exact=True)).to_be_visible()
                            page.screenshot(path=str(output/(name+'-shopping-after.png')))
                            dialog.get_by_role('button', name='关闭', exact=True).click()
                            stage = name+':record-review'
                            page.get_by_role('button', name='记一顿饭', exact=True).click()
                            dialog.get_by_label('食物', exact=True).fill('小米粥')
                            dialog.get_by_label('实际份量', exact=True).fill('几口')
                            dialog.get_by_label('接受情况', exact=True).select_option('吃了一些')
                            dialog.get_by_role('button', name='保存到家庭记录', exact=True).click()
                            expect(page.get_by_role('dialog')).to_have_count(0)
                            page.get_by_role('button', name='回看', exact=True).click()
                            expect(page.locator('.review-day').first.get_by_text('QA午餐', exact=True)).to_be_visible()
                            expect(page.locator('.review-day').first.get_by_text('小米粥', exact=True)).to_be_visible()
                            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth+1')
                            page.screenshot(path=str(output/(name+'-review.png')))
                            stage = name+':caregiver-login'
                            invite = owner.post('/api/invites', json={}).json()['path']
                            other_context = browser.new_context(viewport=viewport)
                            other = other_context.new_page()
                            route_app(other, caregiver)
                            other.goto(ORIGIN+invite)
                            other.get_by_label('你的称呼', exact=True).fill('测试照顾者')
                            other.get_by_role('button', name='确认加入家庭', exact=True).click()
                            expect(other.get_by_role('heading', name=re.compile('测试照顾者，今天好'))).to_be_visible()
                            other.reload()
                            expect(other.get_by_role('heading', name=re.compile('测试照顾者，今天好'))).to_be_visible()
                            other.get_by_role('button', name='回看', exact=True).click()
                            expect(other.locator('.review-day').first.get_by_text('小米粥', exact=True)).to_be_visible()
                            other_context.close()
                            assert not errors, 'JavaScript page errors'
                            context.close()
                            completed.append({'viewport': name, 'checks': ['pantry','reviewed_menu','shopping_refresh','actual_vs_plan','invite_login_and_reload','shared_records','no_horizontal_overflow'], 'status': 'passed'})
        except Exception as exc:
            try:
                target = other if ':caregiver' in stage else page
                target.screenshot(path=str(output/'failure.png'))
            except Exception:
                pass
            detail = re.sub(r'#invite=[^\s]+', '#invite=[redacted]', str(exc))[:1000]
            (output/'result.json').write_text(json.dumps({'mode':'synthetic-browser','status':'failed','stage':stage,'error_type':type(exc).__name__,'detail':detail,'completed':completed},ensure_ascii=False,indent=2))
            raise
        finally:
            browser.close()
    (output/'result.json').write_text(json.dumps({'mode':'synthetic-browser','status':'passed','completed':completed,'wechat':'not_run','live_model':'not_run'},ensure_ascii=False,indent=2))
    return completed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT/'test-results/browser')
    parser.add_argument('--chromium-path')
    args = parser.parse_args()
    if not (ROOT/'dist/index.html').exists():
        parser.error('Build frontend with npm run build first')
    try:
        result = run(args.output, args.chromium_path)
    except Exception as exc:
        print('Browser checks failed; inspect the synthetic report. Error type: '+type(exc).__name__)
        return 1
    print('Browser checks passed for '+', '.join(i['viewport'] for i in result)+'. Synthetic provider; not WeChat or live-model verification.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
