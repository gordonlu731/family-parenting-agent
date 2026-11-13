import contextlib
from datetime import datetime, timedelta, timezone
import io
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import httpx
import test_app as base
from scripts import evaluate, operations


class OperationsTest(unittest.TestCase):
    setUp = base.SharedFamilyTest.setUp
    tearDown = base.SharedFamilyTest.tearDown
    post_record = base.SharedFamilyTest.post_record
    payload = base.SharedFamilyTest.payload

    @property
    def source(self): return Path(self.tmp.name)/'family.db'

    @property
    def destination(self): return Path(self.tmp.name)/'snapshots'

    def test_backup_includes_committed_wal_and_restore_is_isolated(self):
        self.post_record()
        with base.mod.database(True) as writer:
            writer.execute('UPDATE records SET note=?', ('not committed',))
            result=operations.backup(self.source,self.destination)
        path=self.destination/result['backup']
        self.assertFalse(result['encrypted']);self.assertFalse(result['off_host'])
        self.assertEqual(path.stat().st_mode&0o777,0o600)
        self.assertEqual(path.with_suffix('.json').stat().st_mode&0o777,0o600)
        with sqlite3.connect(path) as db:self.assertEqual(db.execute('SELECT note FROM records').fetchone()[0],'')
        with base.mod.database() as db:self.assertEqual(db.execute('SELECT note FROM records').fetchone()[0],'not committed')
        original=operations.digest(self.source)
        self.assertEqual(operations.restore_check(path)['status'],'ok')
        self.assertEqual(operations.digest(self.source),original)

    def test_retention_only_prunes_valid_owned_backup_pairs(self):
        results=[operations.backup(self.source,self.destination,keep=2) for _ in range(3)]
        unrelated=self.destination/'unrelated.sqlite3';unrelated.write_text('keep this')
        operations.backup(self.source,self.destination,keep=2)
        self.assertEqual(len(list(self.destination.glob('family-backup-*.sqlite3'))),2)
        self.assertEqual(len(list(self.destination.glob('family-backup-*.json'))),2)
        self.assertTrue(unrelated.exists())

    def test_missing_source_and_unsafe_paths_never_create_empty_database(self):
        missing=Path(self.tmp.name)/'absent.db'
        with self.assertRaises(operations.OperationError):operations.backup(missing,self.destination)
        self.assertFalse(missing.exists());self.assertFalse(self.destination.exists())
        alias=Path(self.tmp.name)/'alias.db';alias.symlink_to(self.source)
        with self.assertRaises(operations.OperationError):operations.backup(alias,self.destination)
        self.destination.mkdir(mode=0o755)
        with self.assertRaises(operations.OperationError):operations.backup(self.source,self.destination)

    def test_retention_failure_keeps_the_new_complete_backup(self):
        operations.backup(self.source,self.destination,keep=2)
        operations.backup(self.source,self.destination,keep=2)
        original=Path.unlink
        def fail_pruning(path,*args,**kwargs):
            if path.suffix=='.json':raise OSError('synthetic cleanup failure')
            return original(path,*args,**kwargs)
        with patch.object(Path,'unlink',fail_pruning),self.assertRaises(OSError):
            operations.backup(self.source,self.destination,keep=2)
        self.assertEqual(len(list(self.destination.glob('family-backup-*.sqlite3'))),3)
        self.assertTrue(all(operations.verify_backup(p) for p in self.destination.glob('family-backup-*.sqlite3')))

    def test_checksum_corruption_and_concurrent_backup_are_rejected(self):
        result=operations.backup(self.source,self.destination)
        path=self.destination/result['backup']
        with operations.backup_lock(self.destination),self.assertRaises(operations.OperationError):
            operations.backup(self.source,self.destination)
        with path.open('ab') as stream:stream.write(b'corruption')
        with self.assertRaisesRegex(operations.OperationError,'checksum'):
            operations.restore_check(path)

    def test_monitor_reports_missing_stale_and_low_disk_without_secrets(self):
        result=operations.check(self.source,self.destination)
        self.assertIn('backup_missing',result['issues'])
        result=operations.backup(self.source,self.destination)
        self.assertEqual(operations.check(self.source,self.destination)['status'],'ok')
        manifest=(self.destination/result['backup']).with_suffix('.json')
        data=json.loads(manifest.read_text());data['created_at']=(datetime.now(timezone.utc)-timedelta(days=3)).isoformat();manifest.write_text(json.dumps(data))
        result=operations.check(self.source,self.destination)
        self.assertIn('backup_stale_or_clock_mismatch',result['issues'])
        with patch.object(operations.shutil,'disk_usage',return_value=type('Usage',(),{'free':0})()):
            self.assertIn('disk_space_low_or_path_missing',operations.check(self.source,self.destination)['issues'])
        self.assertNotIn(self.token,json.dumps(result))

    def test_health_checks_database_without_creating_a_missing_file(self):
        self.assertEqual(self.owner.get('/api/health').status_code,200)
        self.source.unlink()
        result=self.owner.get('/api/health')
        self.assertEqual(result.status_code,503)
        self.assertEqual(result.json(),{'status':'unavailable'})
        self.assertFalse(self.source.exists())


class EvaluationToolTest(unittest.TestCase):
    def cases(self):return json.loads((evaluate.ROOT/'evals/family-scenarios.json').read_text())

    def test_default_dry_run_never_opens_database_or_provider(self):
        with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,{'APP_DB':str(Path(tmp)/'must-not-exist.db')}),patch.object(evaluate,'run',side_effect=AssertionError('must not run')):
            output=io.StringIO()
            with contextlib.redirect_stdout(output):self.assertEqual(evaluate.main(['--all']),0)
            self.assertEqual(json.loads(output.getvalue())['provider_calls'],0)
            self.assertFalse((Path(tmp)/'must-not-exist.db').exists())

    def test_live_requires_configuration_and_valid_output_before_calling(self):
        with patch.dict(os.environ,{'MODEL_API_KEY':'','MODEL_BASE_URL':'','MODEL_ID':''}),self.assertRaises(SystemExit):
            with contextlib.redirect_stderr(io.StringIO()):evaluate.main(['--call-model'])
        with patch.dict(os.environ,{'MODEL_API_KEY':'synthetic-secret','MODEL_BASE_URL':'https://model.example/v1','MODEL_ID':'synthetic'}),patch.object(evaluate,'run',side_effect=AssertionError('must not run')),self.assertRaises(SystemExit):
            with contextlib.redirect_stderr(io.StringIO()):evaluate.main(['--call-model','--output',str(evaluate.ROOT/'public-report.json')])

    def test_all_mocked_scenarios_validate_runner_but_not_model_quality(self):
        report=evaluate.run(self.cases(),mock=True)
        self.assertEqual(len(report['cases']),30)
        self.assertTrue(all(c['machine_status']=='passed' for c in report['cases']))
        self.assertEqual(report['provider_calls'],0)
        self.assertFalse(report['quality_certified'])
        self.assertEqual(report['mode'],'mock_model')
        self.assertTrue(all(c['status']=='not_run' for c in self.cases()))

    def test_provider_budget_is_a_hard_request_count_and_preserves_real_database(self):
        sent=[]
        class FakeRemote:
            def __init__(self,**kwargs):pass
            async def __aenter__(self):return self
            async def __aexit__(self,*args):pass
            async def post(self,url,**kwargs):
                sent.append(kwargs['json'])
                content=json.dumps(evaluate.mock_output('r01',kwargs['json']),ensure_ascii=False)
                return httpx.Response(200,request=httpx.Request('POST',url),json={'choices':[{'message':{'content':content},'finish_reason':'stop'}]})
        with tempfile.TemporaryDirectory() as tmp:
            sentinel=Path(tmp)/'production.db';sentinel.write_bytes(b'do not touch')
            env={'APP_DB':str(sentinel),'MODEL_API_KEY':'synthetic-secret','MODEL_BASE_URL':'https://model.example/v1','MODEL_ID':'synthetic'}
            with patch.dict(os.environ,env),patch('httpx.AsyncClient',FakeRemote):
                report=evaluate.run(self.cases()[:2],mock=False,max_calls=1)
            self.assertEqual(sentinel.read_bytes(),b'do not touch')
        self.assertEqual(len(sent),1)
        self.assertEqual(report['provider_calls'],1)
        self.assertEqual(report['cases'][1]['reason'],'provider_call_budget_exhausted')
        self.assertNotIn('synthetic-secret',json.dumps(report))

    def test_report_permissions_refuse_overwrite_and_scrub_identity_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'private.json';evaluate.write_report(path,{'mode':'test'})
            self.assertEqual(path.stat().st_mode&0o777,0o600)
            with self.assertRaises(FileExistsError):evaluate.write_report(path,{})
        self.assertEqual(evaluate.scrub({'id':'private','csrf':'private','items':[{'family_id':'private','food':'米饭'}]}),{'items':[{'food':'米饭'}]})

    def test_default_report_directory_works_next_to_external_runtime_database(self):
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'production.db';source.write_bytes(b'leave production unchanged')
            with patch.dict(os.environ,{'APP_DB':str(source),'EVAL_REPORT_DIR':''}),contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(evaluate.main(['--mock-model','--cases','r04']),0)
            self.assertEqual(source.read_bytes(),b'leave production unchanged')
            reports=list((Path(tmp)/'evaluations').glob('*.json'))
            self.assertEqual(len(reports),1)
            self.assertEqual(reports[0].stat().st_mode&0o777,0o600)
            self.assertEqual(json.loads(reports[0].read_text())['provider_calls'],0)
