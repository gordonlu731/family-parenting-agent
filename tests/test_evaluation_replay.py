"""Offline regression diagnostics use fictional fixtures and forbid real transport."""
import contextlib
from copy import deepcopy
from datetime import date,timedelta
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import evaluate


class EvaluationReplayTest(unittest.TestCase):
    def cases(self):
        return [s for s in json.loads((evaluate.ROOT/'evals/family-scenarios.json').read_text()) if s['id']=='p10']

    def captured(self):
        report=evaluate.run(self.cases(),mock=True,capture=True)
        self.assertEqual(report['cases'][0]['machine_status'],'passed')
        self.assertEqual(report['provider_calls'],0)
        self.assertEqual(len(report['provider_replies']),2)
        return report

    def replay(self,entries,**kwargs):
        with patch('httpx.AsyncClient',side_effect=AssertionError('network must not be constructed')):
            return evaluate.run(self.cases(),mock=False,replay=entries,**kwargs)

    def test_two_actor_replay_never_constructs_network_or_opens_production_database(self):
        source=self.captured()
        with tempfile.TemporaryDirectory() as tmp:
            sentinel=Path(tmp)/'production.sqlite3';sentinel.write_bytes(b'production must remain unchanged')
            with patch.dict(os.environ,{'APP_DB':str(sentinel),'MODEL_API_KEY':'private-canary',
                                       'MODEL_BASE_URL':'https://api.deepseek.com','MODEL_ID':'deepseek-flash'}):
                report=self.replay(source['provider_replies'])
            self.assertEqual(sentinel.read_bytes(),b'production must remain unchanged')
        case=report['cases'][0]
        self.assertEqual(report['mode'],'offline_replay')
        self.assertEqual(case['machine_status'],'passed')
        self.assertEqual(report['provider_calls'],0)
        self.assertEqual(report['max_provider_calls'],0)
        self.assertEqual(report['replay_calls'],2)
        self.assertFalse(report['quality_certified'])
        self.assertEqual(case['human_review'],'pending')
        steps={s['step'] for s in case['steps']}
        self.assertIn('flow.replacement_preserves_other_meal',steps)
        self.assertIn('flow.replacement_preserves_actual_record',steps)
        self.assertIn('flow.shared_stock_updated',steps)
        self.assertNotIn('private-canary',json.dumps(report))
        self.assertNotIn(str(sentinel),json.dumps(report))

    def test_provider_success_does_not_hide_invalid_replacement_or_fallback_to_network(self):
        entries=deepcopy(self.captured()['provider_replies'])
        body=json.loads(entries[1]['body']['choices'][0]['message']['content'])
        body['meals'][0]['meal']='早餐'
        entries[1]['body']['choices'][0]['message']['content']=json.dumps(body,ensure_ascii=False)
        report=self.replay(entries)
        case=report['cases'][0]
        self.assertEqual(case['machine_status'],'failed')
        self.assertEqual(case['failure_step'],'http.menu_proposals')
        self.assertEqual(case['steps'][-1]['expected'],200)
        self.assertEqual(case['steps'][-1]['actual'],502)
        self.assertTrue(case['failure_location']['source'].startswith('scripts/'))
        self.assertEqual(report['provider_calls'],0)

    def test_business_mutation_is_caught_by_named_checkpoint_without_weakening_assertion(self):
        entries=self.captured()['provider_replies']
        original=evaluate.Case.confirm
        def corrupt_other_meal(case,proposal,expected=200):
            result=original(case,proposal,expected)
            if proposal['payload']['meals'][0]['title'].startswith('QA替换'):
                with case.mod.database(True) as db:
                    db.execute('UPDATE menus SET title=? WHERE meal=?',('injected regression','晚餐'))
            return result
        with patch.object(evaluate.Case,'confirm',corrupt_other_meal):
            report=self.replay(entries)
        self.assertEqual(report['cases'][0]['failure_step'],'flow.replacement_preserves_other_meal')
        self.assertEqual(report['cases'][0]['machine_status'],'failed')
        self.assertEqual(report['provider_calls'],0)

    def test_missing_mismatched_or_unused_replies_fail_without_network_fallback(self):
        entries=self.captured()['provider_replies']
        wrong=deepcopy(entries);wrong[1]['operation']='menu'
        for values,reason in [(entries[:1],'replay_reply_missing'),(wrong,'replay_operation_mismatch'),
                              (entries+[deepcopy(entries[-1])],'replay_replies_unused')]:
            with self.subTest(reason=reason):
                report=self.replay(values)
                self.assertEqual(report['cases'][0]['reason'],reason)
                self.assertEqual(report['cases'][0]['machine_status'],'failed')
                self.assertEqual(report['provider_calls'],0)

    def test_old_reports_and_unsafe_replay_files_are_rejected_before_execution(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'old.json';path.write_text('{"cases":[]}');path.chmod(0o600)
            with self.assertRaisesRegex(ValueError,'unsaved'):evaluate.load_replay(path)
            with patch.object(evaluate,'run',side_effect=AssertionError('must not run')), contextlib.redirect_stderr(io.StringIO()),self.assertRaises(SystemExit):
                evaluate.main(['--replay',str(path),'--cases','p10'])
            path.write_text(json.dumps(self.captured()));path.chmod(0o644)
            with self.assertRaises(ValueError):evaluate.load_replay(path)
            path.chmod(0o600)
            alias=Path(tmp)/'link.json';alias.symlink_to(path)
            with self.assertRaises(ValueError):evaluate.load_replay(alias)
            self.assertEqual(len(evaluate.load_replay(path)),2)

    def test_date_rebasing_is_explicit_marked_and_does_not_rewrite_fixture(self):
        entries=deepcopy(self.captured()['provider_replies'])
        for entry in entries:
            entry['request_start']=(date.fromisoformat(entry['request_start'])-timedelta(days=1)).isoformat()
            body=json.loads(entry['body']['choices'][0]['message']['content'])
            for meal in body['meals']:
                meal['day']=(date.fromisoformat(meal['day'])-timedelta(days=1)).isoformat()
            entry['body']['choices'][0]['message']['content']=json.dumps(body,ensure_ascii=False)
        before=deepcopy(entries)
        failed=self.replay(entries)
        self.assertEqual(failed['cases'][0]['reason'],'replay_date_mismatch')
        report=self.replay(entries,rebase=True)
        self.assertTrue(report['replay_date_rebasing'])
        self.assertEqual(report['cases'][0]['machine_status'],'passed')
        self.assertEqual(entries,before)

    def test_capture_is_private_persisted_before_case_failure_and_does_not_echo_exception(self):
        def fail_after_reply(case,tracker):
            case.menu()
            saved=json.loads(target.read_text())
            self.assertEqual(saved['status'],'running')
            self.assertEqual(len(saved['provider_replies']),1)
            seen.append(True)
            raise AssertionError('private-exception-canary')
        with tempfile.TemporaryDirectory() as tmp:
            target=Path(tmp)/'report.json';seen=[]
            with patch.object(evaluate,'execute',side_effect=fail_after_reply), contextlib.redirect_stdout(io.StringIO()) as output:
                result=evaluate.main(['--mock-model','--cases','p10','--capture-responses','--output',str(target)])
            self.assertEqual(result,1)
            self.assertEqual(seen,[True])
            report=json.loads(target.read_text())
            self.assertEqual(target.stat().st_mode&0o777,0o600)
            self.assertEqual(len(report['provider_replies']),1)
            self.assertIsNotNone(report['cases'][0]['failure_location'])
            self.assertNotIn('private-exception-canary',target.read_text()+output.getvalue())
            self.assertNotIn('csrf',target.read_text())
            self.assertNotIn('Authorization',target.read_text())
            self.assertNotIn('messages',json.dumps(report['provider_replies']))
            self.assertNotIn('虚构',output.getvalue())

    def test_capture_drops_provider_error_bodies_and_auth_headers(self):
        import httpx
        tracker=evaluate.ProviderTracker(False,1,capture=True);tracker.case_id='p10'
        response=httpx.Response(401,text='private-provider-error-canary',
                                headers={'Authorization':'private-header-canary'})
        tracker.remember(response,{'messages':[{'content':'system'},
            {'content':json.dumps({'request':{'start':'2026-01-01'}})}]})
        saved=json.dumps(tracker.captured)
        self.assertNotIn('private-provider-error-canary',saved)
        self.assertNotIn('private-header-canary',saved)
        self.assertEqual(tracker.captured[0]['body'],{})

    def test_relative_record_dates_rebase_with_the_captured_reference_day(self):
        cases=[s for s in json.loads((evaluate.ROOT/'evals/family-scenarios.json').read_text()) if s['id']=='r02']
        entries=evaluate.run(cases,mock=True,capture=True)['provider_replies']
        entry=entries[0]
        entry['request_start']=(date.fromisoformat(entry['request_start'])-timedelta(days=1)).isoformat()
        content=json.loads(entry['body']['choices'][0]['message']['content'])
        content['day']=(date.fromisoformat(content['day'])-timedelta(days=1)).isoformat()
        entry['body']['choices'][0]['message']['content']=json.dumps(content,ensure_ascii=False)
        with patch('httpx.AsyncClient',side_effect=AssertionError('no network')):
            report=evaluate.run(cases,replay=entries,rebase=True)
        self.assertEqual(report['cases'][0]['machine_status'],'passed')
        self.assertTrue(report['replay_date_rebasing'])
        self.assertEqual(report['provider_calls'],0)

    def test_setup_failure_is_reported_and_original_exception_text_is_private(self):
        def fail_setup(case,**changes):
            case.check(False,'setup.profile_refused',expected=200,actual=409)
        with patch.object(evaluate.Case,'profile',fail_setup):
            report=evaluate.run(self.cases(),mock=True,capture=True)
        self.assertEqual(report['cases'][0]['machine_status'],'failed')
        self.assertEqual(report['cases'][0]['failure_step'],'setup.profile_refused')
        self.assertEqual(report['provider_calls'],0)
        self.assertEqual(report['provider_replies'],[])
