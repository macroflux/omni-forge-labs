"""Core release checks runnable without pytest or Flask (PyYAML is required).

Run: python -m unittest discover -s tests -p test_smoke_unittest.py -v
"""
import contextlib
import hashlib
import io
import multiprocessing
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT/'omniforge'/'runner'))
import forge
from adapters.local_board import LocalBoard
from omniforge.viewer.worker import _is_runnable
import yaml


def write_events(path, number):
    board = LocalBoard(path)
    for i in range(20):
        board.append_history('SHARED', {'writer':number, 'index':i})


class ReleaseChecks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for name, value in [('_RUNS_DIR',str(self.root/'runs')), ('_WORK_DIR',str(self.root/'work'))]:
            context = patch.object(forge, name, value)
            context.start(); self.addCleanup(context.stop)
        self.board = LocalBoard(str(self.root/'board.json'))

    def run_demo(self, auto=False):
        with contextlib.redirect_stdout(io.StringIO()):
            return forge.run_project('demo', 'DEMO-1', auto=auto, board=self.board)

    def test_demo_auto_produces_all_artifacts_and_bundle(self):
        self.assertTrue(self.run_demo(auto=True))
        state = self.board.get_ticket('DEMO-1')
        for stage, name in forge.STAGE_ARTIFACTS.items():
            self.assertTrue(Path(state['run_dir'],stage,name).is_file())
        import zipfile, json
        with zipfile.ZipFile(Path(state['run_dir'],'deliver','demo-bundle.zip')) as bundle:
            self.assertEqual(json.loads(bundle.read('result.json'))['items'], [1,2,3])
        self.assertTrue(any(x.get('event') == 'auto_override' for x in state['history']))

    def test_manual_gates_resume_and_preserve_previous_evidence(self):
        saved=[]
        for gate in ('design','test','deliver'):
            self.assertFalse(self.run_demo())
            state=self.board.get_ticket('DEMO-1')
            self.assertEqual(state['status'],'paused_at_'+gate)
            report=Path(state['run_dir'],'run_report.md')
            saved.append((report,report.read_bytes()))
            self.board.approve_stage('DEMO-1',gate,by='reviewer')
            self.assertTrue(_is_runnable(self.board.get_ticket('DEMO-1')))
        self.assertTrue(self.run_demo())
        for file,content in saved:self.assertEqual(file.read_bytes(),content)
        self.assertFalse(self.board.get_ticket('DEMO-1')['approvals'])

    def test_approval_rejects_missing_or_wrong_gate(self):
        with self.assertRaises(ValueError):self.board.approve_stage('MISSING','test')
        self.run_demo()
        with self.assertRaises(ValueError):self.board.approve_stage('DEMO-1','deliver')

    def test_changed_evidence_invalidates_approval(self):
        self.run_demo();self.board.approve_stage('DEMO-1','design');self.run_demo()
        state=self.board.get_ticket('DEMO-1')
        self.assertEqual(state['status'],'paused_at_test')
        self.board.approve_stage('DEMO-1','test')
        Path(state['run_dir'],'implement','implementation.md').write_text('changed',encoding='utf-8')
        self.assertFalse(self.run_demo())
        self.assertEqual(self.board.get_ticket('DEMO-1')['status'],'paused_at_test')

    def test_workspace_change_restarts_and_requires_review(self):
        self.run_demo();self.board.approve_stage('DEMO-1','design');self.run_demo()
        self.board.approve_stage('DEMO-1','test')
        work=self.root/'work'/'DEMO-1';work.mkdir(parents=True)
        (work/'plan.md').write_text('new scope',encoding='utf-8')
        self.assertFalse(self.run_demo())
        state=self.board.get_ticket('DEMO-1')
        self.assertEqual(state['status'],'paused_at_design')

    def test_config_change_requires_new_review(self):
        self.run_demo(); self.board.approve_stage('DEMO-1','design')
        manifest=forge.load_manifest('demo'); manifest['description']='new requirements'
        with patch.object(forge,'load_manifest',return_value=manifest):
            self.assertFalse(self.run_demo())
        self.assertEqual(self.board.get_ticket('DEMO-1')['status'],'paused_at_design')

    def test_failed_stage_records_retry_and_report(self):
        manifest={'stages':{'implement':['exit 9']},'repo_root':str(self.root)}
        with patch.object(forge,'load_manifest',return_value=manifest), patch.object(forge,'load_gates',return_value={'rollback':{'implement':'design'}}):
            self.assertFalse(self.run_demo(auto=True))
        state=self.board.get_ticket('DEMO-1')
        self.assertEqual(state['status'],'failed_at_implement')
        self.assertEqual(state['rollback_to'],'design')
        self.assertIn('exit 9',Path(state['run_dir'],'run_report.md').read_text(encoding='utf-8'))

    def test_invalid_configuration_is_rejected(self):
        for manifest in ({'stages':{}},{'stages':{'typo':[]}},{'stages':{'test':[42]}}):
            with self.assertRaises(ValueError):forge.validate_config(manifest, {})

    def test_invalid_resume_does_not_claim_running(self):
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertFalse(forge.run_project('demo','DEMO-1',force_stage='typo',board=self.board))
        self.assertIsNone(self.board.get_ticket('DEMO-1'))

    def test_double_claim_is_rejected(self):
        self.board.claim_run('X', {'status':'running'})
        with self.assertRaises(ValueError):self.board.claim_run('X', {'status':'running'})

    def test_worker_allowlist_and_retry_budget(self):
        for status in ('held','cancelled','unknown','running','delivered','paused_at_test'):
            self.assertFalse(_is_runnable({'status':status}))
        self.assertFalse(_is_runnable({'status':'failed_at_test','rollback_to':'implement','rollback_counts':{'test':3}}))
        self.assertTrue(_is_runnable({'status':'pending'}))

    def test_board_concurrent_history_writes(self):
        ctx=multiprocessing.get_context('spawn')
        processes=[ctx.Process(target=write_events,args=(self.board.board_path,i)) for i in range(3)]
        for process in processes:process.start()
        for process in processes:
            process.join(30)
            if process.is_alive():process.terminate();process.join()
            self.assertEqual(process.exitcode,0)
        self.assertEqual(len(self.board.get_ticket('SHARED')['history']),60)

    def test_cli_failure_returns_nonzero(self):
        proc=subprocess.run([sys.executable,'-m','omniforge.runner.forge','run','--project','demo','--ticket','CLI-CHECK','--force-stage','typo'],cwd=ROOT,capture_output=True)
        self.assertEqual(proc.returncode,1)


if __name__ == '__main__':unittest.main()
