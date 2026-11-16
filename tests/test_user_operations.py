import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import user_operations


class UserOperationsTest(unittest.TestCase):
    @unittest.skipUnless(shutil.which('systemd-analyze'),'real parser unavailable')
    def test_real_parser_accepts_native_timers_and_private_commands(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp);root=base/'release %n space'
            exe=root/'.venv/bin/python';exe.parent.mkdir(parents=True)
            exe.write_text('#!/bin/sh\nexit 0\n');exe.chmod(0o700)
            units=user_operations.units(root,base/'data',base/'backups')
            for name,body in units.items():(base/name).write_text(body)
            result=subprocess.run(['systemd-analyze','--user','--man=no','verify',
                *[str(base/n) for n in units]],capture_output=True,text=True,timeout=15,
                env={**os.environ,'XDG_RUNTIME_DIR':str(base)})
            self.assertEqual(result.returncode,0,result.stderr)
            body='\n'.join(units.values())
            self.assertNotIn('docker',body);self.assertNotIn('sudo',body)
            self.assertNotIn('restart',body);self.assertNotIn('.env',body)
            self.assertIn('Asia/Shanghai',body);self.assertIn('OnUnitActiveSec=1h',body)
