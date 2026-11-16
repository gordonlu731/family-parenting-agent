import contextlib
import io
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import preview_config as preview
from deploy import read_env,write_config


class PreviewConfigTest(unittest.TestCase):
    def test_only_origin_cookie_and_key_change(self):
        body='BOOTSTRAP_TOKEN=unchanged\nPUBLIC_ORIGIN=http://127.0.0.1:18080\nCOOKIE_SECURE=false\nMODEL_API_KEY=SYNTHETIC_PRIVATE\nMODEL_DAILY_REQUEST_LIMIT=30\n'
        result=preview.candidate(body,'https://synthetic.example.ts.net')
        self.assertIn('BOOTSTRAP_TOKEN=unchanged',result)
        self.assertIn('MODEL_DAILY_REQUEST_LIMIT=30',result)
        self.assertIn('MODEL_API_KEY=\n',result);self.assertNotIn('SYNTHETIC_PRIVATE',result)
        self.assertIn('COOKIE_SECURE=true',result)
        for origin in ['https://synthetic.example.ts.net/','http://synthetic.example.ts.net','https://x.ts.net\nMODEL_API_KEY=bad','https://example.com']:
            with self.assertRaises(ValueError):preview.candidate(body,origin)

    def test_preparation_preserves_active_config_and_rejects_unknown_change(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp);root=base/'release';root.mkdir(mode=0o700)
            data=base/'data';data.mkdir(mode=0o700)
            for name in ['backend/app.py','dist/index.html','.venv/bin/python']:
                p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('synthetic')
            with contextlib.redirect_stdout(io.StringIO()):
                write_config(root/'.env','private',18080,origin='',base='https://api.deepseek.com',model='deepseek-flash',key='SYNTHETIC_PRIVATE')
            old=(root/'.env').read_bytes();state=base/'preview'
            preview.prepare(root,data,state,'https://synthetic.example.ts.net')
            preview.prepare(root,data,state,'https://synthetic.example.ts.net')
            self.assertEqual((root/'.env').read_bytes(),old)
            self.assertEqual((state/'app.env.preview').stat().st_mode&0o777,0o600)
            self.assertEqual(read_env(state/'app.env.preview')['MODEL_API_KEY'],'')
            def response(url,timeout):
                r=io.BytesIO(b'{"model_ready":false,"demo_mode":false}' if url.endswith('/config') else b'{"status":"ok"}')
                r.status=200
                return r
            with patch.dict(os.environ),patch.object(preview.subprocess,'run') as restart,patch.object(preview.urllib.request,'build_opener') as opener:
                opener.return_value.open.side_effect=response
                self.assertEqual(preview.change(state)['status'],'applied')
                self.assertEqual(read_env(root/'.env')['MODEL_API_KEY'],'')
                self.assertEqual(preview.change(state,True)['status'],'restored')
                self.assertEqual((root/'.env').read_bytes(),old)
                self.assertEqual(restart.call_count,2)
            (root/'.env').write_text('unknown concurrent edit')
            with patch.object(preview.subprocess,'run',side_effect=AssertionError('must not restart')),self.assertRaises(ValueError):preview.change(state)
            self.assertEqual((root/'.env').read_text(),'unknown concurrent edit')
