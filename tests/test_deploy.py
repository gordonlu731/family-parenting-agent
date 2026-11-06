import contextlib
import io
import json
import os
from pathlib import Path
import socket
import tempfile
import unittest
from unittest.mock import patch

import httpx

from backend.provider import build_body, failure_message
from scripts import deploy, check_model


class DeploymentTest(unittest.TestCase):
    def configure(self, directory, mode='private', values=None):
        responses=iter(values or ['', ''])
        with contextlib.redirect_stdout(io.StringIO()) as output:
            result=deploy.configure(Path(directory)/'.env',mode,18080,ask=lambda _:next(responses),secret=lambda _:'sk-private-test-only')
        return result,output.getvalue()

    def test_config_is_private_and_secret_is_never_printed(self):
        with tempfile.TemporaryDirectory() as tmp:
            env,output=self.configure(tmp)
            file=Path(tmp)/'.env'
            self.assertEqual(file.stat().st_mode & 0o777,0o600)
            self.assertEqual(env['PUBLIC_ORIGIN'],'http://127.0.0.1:18080')
            self.assertEqual(env['COOKIE_SECURE'],'false')
            self.assertEqual(env['MODEL_ENABLE_THINKING'],'false')
            self.assertGreaterEqual(len(env['BOOTSTRAP_TOKEN']),32)
            self.assertNotIn(env['MODEL_API_KEY'],output)
            self.assertNotIn(env['BOOTSTRAP_TOKEN'],output)
            self.assertEqual(deploy.read_env(file),env)

    def test_existing_env_and_symlink_are_never_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.configure(tmp)
            file=Path(tmp)/'.env';original=file.read_bytes()
            with self.assertRaises(ValueError):self.configure(tmp)
            self.assertEqual(file.read_bytes(),original)
            alias=Path(tmp)/'.env-alias';alias.symlink_to(file)
            with self.assertRaises(ValueError):deploy.configure(alias,'private',18080)

    def test_https_config_rejects_credentials_paths_and_injection(self):
        for value in ('http://model.example/v1','https://key@model.example/v1','https://model.example/v1?key=secret',"https://model.example/v1\nOTHER=secret",'https://{WorkspaceId}.example/v1','https://model.example/v1/chat/completions'):
            with self.subTest(value=value),self.assertRaises(ValueError):deploy.https_url(value)
        with self.assertRaises(ValueError):deploy.https_url('https://family.example/private',True)

    def test_production_config_keeps_secure_cookie(self):
        with tempfile.TemporaryDirectory() as tmp:
            env,_=self.configure(tmp,'production',['https://family.example','',''])
            self.assertEqual(env['PUBLIC_ORIGIN'],'https://family.example')
            self.assertEqual(env['COOKIE_SECURE'],'true')

    def test_unknown_model_does_not_get_qwen_parameter(self):
        with tempfile.TemporaryDirectory() as tmp:
            env,_=self.configure(tmp,values=['https://other.example/v1','other-model'])
            self.assertEqual(env['MODEL_ENABLE_THINKING'],'')
        with patch.dict(os.environ,{'MODEL_ID':'other-model','MODEL_ENABLE_THINKING':''}):
            self.assertNotIn('enable_thinking',build_body([],True))
        with patch.dict(os.environ,{'MODEL_ID':'qwen-plus','MODEL_ENABLE_THINKING':'false'}):
            self.assertIs(build_body([],True)['enable_thinking'],False)

    def test_provider_errors_do_not_echo_sensitive_bodies(self):
        for status,expected in [(401,'鉴权'),(403,'鉴权'),(429,'额度'),(400,'配置'),(404,'配置')]:
            response=httpx.Response(status,text='sk-secret-should-never-appear',request=httpx.Request('POST','https://model.example'))
            try:response.raise_for_status()
            except httpx.HTTPStatusError as exc:message=failure_message(exc)
            self.assertIn(expected,message)
            self.assertNotIn('sk-secret',message)

    def test_preflight_is_read_only_and_occupied_port_is_reported(self):
        with tempfile.TemporaryDirectory() as tmp,socket.socket() as sock:
            self.configure(tmp)
            sock.bind(('127.0.0.1',0));sock.listen()
            file=Path(tmp)/'.env'
            file.write_text(file.read_text().replace('APP_PORT=18080',f'APP_PORT={sock.getsockname()[1]}').replace('http://127.0.0.1:18080',f'http://127.0.0.1:{sock.getsockname()[1]}'))
            before=file.read_bytes()
            with patch.object(deploy.shutil,'which',return_value='/usr/bin/docker'),patch.object(deploy,'command_ok',return_value=True),contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertFalse(deploy.preflight(file))
            self.assertEqual(file.read_bytes(),before)
            self.assertIn('已占用',output.getvalue())
            self.assertNotIn('sk-private',output.getvalue())

    def test_model_smoke_test_uses_only_synthetic_payload(self):
        bodies=[]
        def handler(request):
            bodies.append(json.loads(request.content))
            return httpx.Response(200,json={'choices':[{'finish_reason':'stop','message':{'content':'{"ok":true}'}}]})
        def client(**kwargs):return httpx.Client(transport=httpx.MockTransport(handler),**kwargs)
        with patch.dict(os.environ,{'MODEL_API_KEY':'sk-not-real','MODEL_ID':'qwen-plus','MODEL_BASE_URL':'https://model.example/v1','MODEL_ENABLE_THINKING':'false'}),contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(check_model.check(client),0)
        self.assertEqual(len(bodies),1)
        self.assertEqual(bodies[0]['response_format'],{'type':'json_object'})
        self.assertEqual(len(bodies[0]['messages']),1)
        self.assertNotIn('sk-not-real',output.getvalue())

    def test_truncated_smoke_reply_is_not_success(self):
        def client(**kwargs):
            return httpx.Client(transport=httpx.MockTransport(lambda request:httpx.Response(200,json={'choices':[{'finish_reason':'length','message':{'content':'{"ok":true}'}}]})),**kwargs)
        with patch.dict(os.environ,{'MODEL_API_KEY':'sk-not-real','MODEL_ID':'qwen-plus','MODEL_BASE_URL':'https://model.example/v1','MODEL_ENABLE_THINKING':'false'}),contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(check_model.check(client),1)
        self.assertNotIn('测试通过',output.getvalue())
