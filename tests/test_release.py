"""Regression checks for v0.1 state, evidence, and concurrency guarantees."""
import json
import multiprocessing
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml
import forge
from omniforge.runner.adapters.local_board import LocalBoard
from omniforge.viewer import worker


@pytest.fixture
def project(tmp_path, monkeypatch):
    folder = tmp_path/'projects'/'sample'
    folder.mkdir(parents=True)
    monkeypatch.setattr(forge, '_PROJECTS_DIR', str(tmp_path/'projects'))
    monkeypatch.setattr(forge, '_RUNS_DIR', str(tmp_path/'runs'))
    monkeypatch.setattr(forge, '_WORK_DIR', str(tmp_path/'work'))
    manifest = {'stages': {'implement': 'demo', 'test':'demo'}, 'repo_root':str(tmp_path)}
    (folder/'manifest.yaml').write_text(yaml.safe_dump(manifest), encoding='utf-8')
    (folder/'gates.yaml').write_text(yaml.safe_dump({'pause_at':['test']}), encoding='utf-8')
    def command(cmd, cwd, log_path, extra_env=None):
        stage = Path(extra_env['FORGE_STAGE_DIR'])
        (stage/forge.STAGE_ARTIFACTS[stage.name]).write_text('evidence', encoding='utf-8')
        return 0
    monkeypatch.setattr(forge, 'run_command', command)
    return LocalBoard(str(tmp_path/'board.json')), folder


def test_empty_manifest_rejected(project):
    board, folder = project
    (folder/'manifest.yaml').write_text('stages: {}', encoding='utf-8')
    with pytest.raises(ValueError):
        forge.run_project('sample', 'T-1', board=board)
    assert board.get_ticket('T-1') is None


def test_bad_force_does_not_claim_ticket(project):
    board, _ = project
    assert not forge.run_project('sample', 'T-1', force_stage='typo', board=board)
    assert board.get_ticket('T-1') is None


def test_approval_requeues_and_resumes(project):
    board, _ = project
    assert not forge.run_project('sample', 'T-1', board=board)
    old = board.get_ticket('T-1')['run_dir']
    board.approve_stage('T-1', 'test')
    assert worker._is_runnable(board.get_ticket('T-1'))
    assert forge.run_project('sample', 'T-1', board=board)
    new = board.get_ticket('T-1')['run_dir']
    assert old != new
    assert Path(old, 'implement', 'implementation.md').exists()
    assert Path(new, 'implement', 'implementation.md').exists()
    assert not board.get_ticket('T-1')['approvals']


def test_changed_evidence_requires_reapproval(project):
    board, _ = project
    forge.run_project('sample', 'T-1', board=board)
    board.approve_stage('T-1', 'test')
    state = board.get_ticket('T-1')
    Path(state['run_dir'], 'implement', 'implementation.md').write_text('changed', encoding='utf-8')
    assert not forge.run_project('sample', 'T-1', board=board)
    assert board.get_ticket('T-1')['status'] == 'paused_at_test'


def test_changed_configuration_requires_reapproval(project):
    board, folder = project
    forge.run_project('sample', 'T-1', board=board)
    board.approve_stage('T-1', 'test')
    data = yaml.safe_load((folder/'manifest.yaml').read_text(encoding='utf-8'))
    data['description'] = 'changed'
    (folder/'manifest.yaml').write_text(yaml.safe_dump(data), encoding='utf-8')
    assert not forge.run_project('sample', 'T-1', board=board)


def test_changed_workspace_restarts_prior_stage(project, tmp_path):
    board, _ = project
    forge.run_project('sample', 'T-1', board=board)
    board.approve_stage('T-1', 'test')
    work = tmp_path/'work'/'T-1'; work.mkdir(parents=True)
    (work/'design.md').write_text('revised design', encoding='utf-8')
    assert not forge.run_project('sample', 'T-1', board=board)
    state = board.get_ticket('T-1')
    report = Path(state['run_dir'], 'run_report.md').read_text(encoding='utf-8')
    assert '| implement | PASS |' in report
    assert state['status'] == 'paused_at_test'


def test_claim_prevents_duplicate_execution(project):
    board, _ = project
    board.claim_run('T-1', {'status':'running'})
    with pytest.raises(ValueError):
        board.claim_run('T-1', {'status':'running'})


@pytest.mark.parametrize('status', ['held','cancelled','unknown'])
def test_worker_skips_nonrunnable_statuses(status):
    assert not worker._is_runnable({'status':status})


def test_worker_caps_retries():
    assert not worker._is_runnable({'status':'failed_at_test', 'rollback_to':'implement', 'rollback_counts':{'test':3}})


def _write_tickets(path, prefix):
    board = LocalBoard(path)
    for i in range(20):
        board.upsert_ticket(f'{prefix}-{i}', {'status':'pending'})


def test_concurrent_writers_preserve_all_tickets(tmp_path):
    path = str(tmp_path/'board.json')
    ctx = multiprocessing.get_context('spawn')
    writers = [ctx.Process(target=_write_tickets, args=(path, str(i))) for i in range(3)]
    for proc in writers: proc.start()
    for proc in writers:
        proc.join(30)
        if proc.is_alive():
            proc.terminate(); proc.join()
            pytest.fail('Writer timed out')
        assert proc.exitcode == 0
    assert len(LocalBoard(path).list_tickets()) == 60


def test_demo_all_eight_stages(tmp_path, monkeypatch):
    monkeypatch.setattr(forge, '_RUNS_DIR', str(tmp_path/'runs'))
    monkeypatch.setattr(forge, '_WORK_DIR', str(tmp_path/'work'))
    board = LocalBoard(str(tmp_path/'board.json'))
    assert forge.run_project('demo', 'DEMO-TEST', auto=True, board=board)
    state = board.get_ticket('DEMO-TEST')
    assert Path(state['run_dir'], 'deliver', 'demo-bundle.zip').is_file()
    for stage, filename in forge.STAGE_ARTIFACTS.items():
        assert Path(state['run_dir'], stage, filename).is_file()
