"""Explicit operator command: one paid synthetic JSON-mode model request.

Run inside the app container to use its environment. No family database is
opened; no API key or provider response body is printed.
"""
import argparse
import json
import os
from pathlib import Path
import sys
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import httpx
from backend.provider import build_body, failure_message


def check(client_factory=httpx.Client):
    base = os.getenv('MODEL_BASE_URL', '')
    parsed = urlsplit(base)
    if not all(os.getenv(k) for k in ('MODEL_BASE_URL', 'MODEL_ID', 'MODEL_API_KEY')) or parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password:
        print('未完成有效HTTPS模型配置，没有发起调用。')
        return 1
    try:
        body = build_body([{'role':'user','content':'连接测试：请仅返回JSON对象 {"ok":true}，不要其他内容。'}], True, 128)
        with client_factory(timeout=45, follow_redirects=False) as client:
            response = client.post(base.rstrip('/')+'/chat/completions', headers={'Authorization':'Bearer '+os.environ['MODEL_API_KEY']}, json=body)
            response.raise_for_status()
            choice = response.json()['choices'][0]
            if choice.get('finish_reason') in ('length', 'content_filter') or json.loads(choice['message']['content']) != {'ok': True}:
                raise ValueError('Unexpected JSON')
    except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as exc:
        print(failure_message(exc)+'连通测试未通过；没有读写家庭数据。')
        return 1
    print('模型HTTPS与JSON模式测试通过。仅为合成样例，不代表育儿场景验收；未读写家庭数据。')
    return 0


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--call-model', action='store_true', help='explicitly make one potentially billable provider request')
    args = parser.parse_args()
    if not args.call_model:
        parser.error('只有显式传入--call-model才会调用模型；该测试可能计费且不计入应用内家庭调用次数')
    raise SystemExit(check())
