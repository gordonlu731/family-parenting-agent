"""Provider payload and sanitized errors, shared with the operator smoke check."""
import os
from urllib.parse import urlsplit

import httpx


def build_body(messages, json_mode=False, max_tokens=1000):
    body = {'model': os.environ['MODEL_ID'], 'messages': messages, 'max_tokens': max_tokens}
    thinking = os.getenv('MODEL_ENABLE_THINKING', '').strip().lower()
    if thinking not in ('', 'true', 'false'):
        raise ValueError('MODEL_ENABLE_THINKING must be true, false or empty')
    if urlsplit(os.getenv('MODEL_BASE_URL', '')).hostname == 'api.deepseek.com':
        # Official DeepSeek uses its own switch and defaults to thinking. Our
        # short structured workflows default to non-thinking unless requested.
        body['thinking'] = {'type': 'enabled' if thinking == 'true' else 'disabled'}
    elif thinking:
        body['enable_thinking'] = thinking == 'true'
    if json_mode:
        body['response_format'] = {'type': 'json_object'}
    return body


def failure_message(exc):
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        if status in (401, 403):
            return '模型鉴权失败，请管理员核对 API Key、所属地域和模型权限。'
        if status == 429:
            return '模型服务限流或额度不足，请稍后再试，或请管理员检查服务额度。'
        if status in (400, 404, 422):
            return '模型配置不兼容，请管理员核对服务地址、模型名称、JSON模式和思考模式。'
    if isinstance(exc, httpx.TimeoutException):
        return '等待模型回复超时，请稍后重试。'
    return 'AI 暂时未返回可用结果，请稍后重试。'
