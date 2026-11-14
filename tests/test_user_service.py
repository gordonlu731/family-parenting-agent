"""Owned fixtures only; never start a host service or use a model credential."""
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import user_service as service
from deploy import write_config


class UserServiceTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.base=Path(self.tmp.name)
        self.root=self.base/'release';self.root.mkdir()
        for name in ('backend/app.py','dist/index.html','.venv/bin/python'):
            p=self.root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('# owned synthetic')
        self.data=self.base/'data';self.data.mkdir(mode=0o700)
        with patch('builtins.print'):
            write_config(self.root/'.env','private',18080,origin='',base='https://example.invalid/v1',model='owned',key='OWNED_SYNTHETIC_ONLY')

    def test_private_env_is_explicit_and_container_db_path_is_not_used_on_host(self):
        with patch.dict(os.environ,{'UNRELATED_SECRET':'CANARY'},clear=False):env=service.environment(self.root,self.data)
        self.assertEqual(env['APP_DB'],str(self.data/'family.sqlite3'));self.assertNotIn('UNRELATED_SECRET',env)
        self.assertEqual((self.root/'.env').stat().st_mode&0o777,0o600)
        self.assertFalse((self.data/'family.sqlite3').exists())

    def test_unit_and_install_only_current_user_and_loopback_no_secret_in_unit(self):
        unit=service.unit(self.root,self.data)
        self.assertNotIn('OWNED_SYNTHETIC_ONLY',unit);self.assertNotIn('/var/run/docker.sock',unit)
        calls=[]
        def invoke(args,**kwargs):calls.append(args)
        with patch.object(service,'paths',return_value=(self.root,self.data)):
            result=service.install(self.root,self.data,invoke=invoke,home=self.base/'home')
        self.assertTrue(result['database_retained'])
        self.assertTrue(all(c[:2]==['systemctl','--user'] for c in calls))
        self.assertTrue((self.base/'home/.config/systemd/user'/service.UNIT).exists())

    def test_config_and_data_permissions_or_links_fail_closed(self):
        (self.root/'.env').chmod(0o644)
        with self.assertRaises(ValueError):service.environment(self.root,self.data)
        (self.root/'.env').chmod(0o600)
        link=self.base/'link';link.symlink_to(self.data)
        with self.assertRaises(ValueError):service.environment(self.root,link)

    def test_systemd_specifier_and_path_quoting(self):
        self.assertEqual(service.quote('/owned/%n dir'), '"/owned/%%n dir"')
        with self.assertRaises(ValueError):service.quote('owned\npath')

    @unittest.skipUnless(shutil.which('systemd-analyze'), 'systemd parser unavailable')
    def test_generated_unit_passes_real_systemd_parser_with_special_path(self):
        root=self.base/'release %n with spaces'
        executable=root/'.venv/bin/python'
        executable.parent.mkdir(parents=True)
        executable.write_text('#!/bin/sh\nexit 0\n');executable.chmod(0o700)
        target=self.base/service.UNIT;target.write_text(service.unit(root,self.data))
        runtime=self.base/'runtime';runtime.mkdir(mode=0o700)
        result=subprocess.run(['systemd-analyze','--user','--man=no','verify',str(target)],
                              capture_output=True,text=True,timeout=15,
                              env={**os.environ,'XDG_RUNTIME_DIR':str(runtime)})
        self.assertEqual(result.returncode,0,result.stderr)

    def test_root_is_refused_even_when_paths_exist(self):
        with patch.object(os,'geteuid',return_value=0),self.assertRaises(ValueError):service.paths(self.root,self.data)
