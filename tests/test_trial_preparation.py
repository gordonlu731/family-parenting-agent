import contextlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import prepare_family_trial as trial
import check_https
from deploy import read_env,write_config


class TrialPreparationTest(unittest.TestCase):
    def fixture(self,base):
        root=base/'release';root.mkdir(mode=0o700)
        for name in ['backend/app.py','dist/index.html','.venv/bin/python']:
            p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('synthetic')
        source=base/'old.env'
        with contextlib.redirect_stdout(io.StringIO()):
            write_config(source,'private',18080,origin='',base='https://api.deepseek.com',model='deepseek-flash',key='SYNTHETIC_PRIVATE_KEY')
        return root,base/'data',base/'backups',base/'state',source

    def test_preparation_and_repeat_do_not_initialize_or_rotate_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            args=self.fixture(Path(tmp));old=args[-1].read_bytes()
            with contextlib.redirect_stdout(io.StringIO()) as output:
                first=trial.prepare(*args);secret=read_env(args[0]/'.env')['BOOTSTRAP_TOKEN']
                second=trial.prepare(*args)
            self.assertEqual(first,second)
            self.assertNotIn('SYNTHETIC_PRIVATE_KEY',output.getvalue())
            self.assertEqual(args[-1].read_bytes(),old)
            self.assertNotEqual(secret,read_env(args[-1])['BOOTSTRAP_TOKEN'])
            self.assertFalse(list(args[1].iterdir()))
            self.assertEqual((args[0]/'.env').stat().st_mode&0o777,0o600)
            self.assertFalse(first['activated']);self.assertFalse(first['initialized'])

    def test_https_candidate_secure_config_and_nonempty_data_refusal(self):
        with tempfile.TemporaryDirectory() as tmp:
            args=self.fixture(Path(tmp))
            with contextlib.redirect_stdout(io.StringIO()):trial.prepare(*args,domain='family.example.com')
            env=read_env(args[0]/'.env');self.assertEqual(env['COOKIE_SECURE'],'true')
            self.assertEqual(env['PUBLIC_ORIGIN'],'https://family.example.com')
            self.assertIn('admin off',(args[3]/'candidate/Caddyfile').read_text())
            (args[1]/'existing.sqlite3').write_bytes(b'preserve')
            before=(args[0]/'.env').read_bytes()
            with self.assertRaises(ValueError):trial.prepare(*args,domain='family.example.com')
            self.assertEqual((args[0]/'.env').read_bytes(),before)

    def test_invalid_proxy_domain_is_rejected_before_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            args=self.fixture(Path(tmp))
            for domain in ['family.example.com/','family.example.com {','http://family.example.com','a\nadmin off']:
                with self.subTest(domain=domain),self.assertRaises(ValueError):trial.prepare(*args,domain=domain)
            self.assertFalse((args[0]/'.env').exists())


class FakeResponse(io.BytesIO):
    def __init__(self,status,body,headers=None):
        super().__init__(json.dumps(body).encode());self.status=status;self.headers=headers or {}


class HttpsProbeTest(unittest.TestCase):
    def test_health_anonymous_and_http_redirect_checks_without_model_call(self):
        urls=[]
        def opener(request,timeout):
            urls.append(request.full_url)
            if request.full_url.startswith('http:'):return FakeResponse(308,{}, {'Location':'https://family.example.com/'})
            if request.full_url.endswith('/health'):return FakeResponse(200,{'status':'ok'})
            if request.full_url.endswith('/config'):return FakeResponse(200,{'demo_mode':False})
            return FakeResponse(401,{})
        result=check_https.check('https://family.example.com',opener)
        self.assertEqual(result['status'],'ok');self.assertEqual(result['model_calls'],0)
        self.assertEqual(len(urls),4)

    def test_public_export_or_missing_https_redirect_fails(self):
        def opener(request,timeout):
            if request.full_url.endswith('/health'):return FakeResponse(200,{'status':'ok'})
            if request.full_url.endswith('/config'):return FakeResponse(200,{'demo_mode':False})
            return FakeResponse(200,{})
        result=check_https.check('https://family.example.com',opener)
        self.assertIn('anonymous_export_not_denied',result['issues'])
        self.assertIn('http_https_redirect_failed',result['issues'])
