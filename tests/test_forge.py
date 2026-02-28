"""Tests for forge.py — the OmniForge Labs local runner."""

from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock, patch

import pytest
import yaml

# Ensure the runner directory is on the path so forge.py can import its adapters.
_RUNNER_DIR = os.path.join(
    os.path.dirname(__file__), "..", "omniforge", "runner"
)
sys.path.insert(0, os.path.abspath(_RUNNER_DIR))

import forge  # noqa: E402  (must come after sys.path modification)
from adapters.local_board import LocalBoard  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_manifest(stages: dict | None = None, artifact_folders: list | None = None):
    return {
        "name": "testproject",
        "description": "Test project",
        "stages": stages or {},
        "artifact_folders": artifact_folders or [],
    }


def _make_gates(pause_at=None, rollback=None, escalation_threshold=2):
    return {
        "pause_at": pause_at or [],
        "rollback": rollback or {"test": "implement", "integrate": "implement"},
        "escalation_threshold": escalation_threshold,
    }


# ---------------------------------------------------------------------------
# load_manifest / load_gates
# ---------------------------------------------------------------------------


class TestLoadManifest:
    def test_raises_when_missing(self, tmp_path, monkeypatch):
        monkeypatch.setattr(forge, "_PROJECTS_DIR", str(tmp_path))
        with pytest.raises(FileNotFoundError):
            forge.load_manifest("nonexistent")

    def test_loads_valid_manifest(self, tmp_path, monkeypatch):
        monkeypatch.setattr(forge, "_PROJECTS_DIR", str(tmp_path))
        proj = tmp_path / "myproject"
        proj.mkdir()
        manifest = _make_manifest(stages={"implement": ["echo hi"]})
        (proj / "manifest.yaml").write_text(yaml.dump(manifest), encoding="utf-8")

        result = forge.load_manifest("myproject")
        assert result["name"] == "testproject"
        assert result["stages"]["implement"] == ["echo hi"]


class TestLoadGates:
    def test_raises_when_missing(self, tmp_path, monkeypatch):
        monkeypatch.setattr(forge, "_PROJECTS_DIR", str(tmp_path))
        with pytest.raises(FileNotFoundError):
            forge.load_gates("nonexistent")

    def test_loads_valid_gates(self, tmp_path, monkeypatch):
        monkeypatch.setattr(forge, "_PROJECTS_DIR", str(tmp_path))
        proj = tmp_path / "myproject"
        proj.mkdir()
        gates = _make_gates(pause_at=["design", "test"])
        (proj / "gates.yaml").write_text(yaml.dump(gates), encoding="utf-8")

        result = forge.load_gates("myproject")
        assert "design" in result["pause_at"]
        assert result["rollback"]["test"] == "implement"


# ---------------------------------------------------------------------------
# run_command
# ---------------------------------------------------------------------------


class TestRunCommand:
    def test_success_returns_zero(self, tmp_path):
        log = str(tmp_path / "test.log")
        rc = forge.run_command("echo hello", cwd=str(tmp_path), log_path=log)
        assert rc == 0
        with open(log, encoding="utf-8") as fh:
            assert "hello" in fh.read()

    def test_failure_returns_nonzero(self, tmp_path):
        log = str(tmp_path / "test.log")
        rc = forge.run_command("exit 42", cwd=str(tmp_path), log_path=log)
        assert rc == 42

    def test_appends_to_existing_log(self, tmp_path):
        log = str(tmp_path / "test.log")
        forge.run_command("echo first", cwd=str(tmp_path), log_path=log)
        forge.run_command("echo second", cwd=str(tmp_path), log_path=log)
        with open(log, encoding="utf-8") as fh:
            content = fh.read()
        assert "first" in content
        assert "second" in content


# ---------------------------------------------------------------------------
# run_project
# ---------------------------------------------------------------------------


def _setup_project(tmp_path, monkeypatch, stages=None, pause_at=None, rollback=None):
    """Set up a temporary project with manifest + gates, patch forge paths."""
    monkeypatch.setattr(forge, "_PROJECTS_DIR", str(tmp_path / "projects"))
    monkeypatch.setattr(forge, "_RUNS_DIR", str(tmp_path / "runs"))

    proj = tmp_path / "projects" / "testproject"
    proj.mkdir(parents=True)

    manifest = _make_manifest(stages=stages or {"implement": ["echo impl"], "test": ["echo test_ok"]})
    (proj / "manifest.yaml").write_text(yaml.dump(manifest), encoding="utf-8")

    gates = _make_gates(pause_at=pause_at or [], rollback=rollback or {"test": "implement"})
    (proj / "gates.yaml").write_text(yaml.dump(gates), encoding="utf-8")

    board = LocalBoard(board_path=str(tmp_path / "board.json"))
    return board


class TestRunProject:
    def test_delivers_on_all_passing_stages(self, tmp_path, monkeypatch):
        board = _setup_project(tmp_path, monkeypatch)
        result = forge.run_project("testproject", "T-001", auto=True, board=board)
        assert result is True
        ticket = board.get_ticket("T-001")
        assert ticket["status"] == "delivered"

    def test_fails_and_records_rollback_on_bad_command(self, tmp_path, monkeypatch):
        board = _setup_project(
            tmp_path, monkeypatch,
            stages={"implement": ["exit 1"]},
            rollback={"implement": "design"},
        )
        result = forge.run_project("testproject", "T-001", auto=True, board=board)
        assert result is False
        ticket = board.get_ticket("T-001")
        assert ticket["status"] == "failed_at_implement"
        assert ticket["rollback_to"] == "design"

    def test_sets_last_passed_stage(self, tmp_path, monkeypatch):
        board = _setup_project(
            tmp_path, monkeypatch,
            stages={"implement": ["echo ok"], "test": ["exit 1"]},
            rollback={"test": "implement"},
        )
        forge.run_project("testproject", "T-001", auto=True, board=board)
        ticket = board.get_ticket("T-001")
        assert ticket["last_passed_stage"] == "implement"

    def test_skips_stages_with_no_commands(self, tmp_path, monkeypatch):
        """Stages absent from the manifest are silently skipped."""
        board = _setup_project(
            tmp_path, monkeypatch,
            stages={"deliver": ["echo done"]},
        )
        result = forge.run_project("testproject", "T-001", auto=True, board=board)
        assert result is True

    def test_force_stage_skips_earlier_stages(self, tmp_path, monkeypatch):
        """--force-stage skips stages before the specified one."""
        calls: list[str] = []

        def fake_run_command(cmd, cwd, log_path):
            calls.append(cmd)
            return 0

        board = _setup_project(
            tmp_path, monkeypatch,
            stages={"implement": ["echo impl"], "test": ["echo test_ok"], "deliver": ["echo done"]},
        )
        monkeypatch.setattr(forge, "run_command", fake_run_command)
        forge.run_project("testproject", "T-001", auto=True, force_stage="test", board=board)
        # implement should be skipped
        cmds_str = " ".join(calls)
        assert "echo impl" not in cmds_str
        assert "echo test_ok" in cmds_str

    def test_unknown_force_stage_returns_false(self, tmp_path, monkeypatch):
        board = _setup_project(tmp_path, monkeypatch)
        result = forge.run_project(
            "testproject", "T-001", auto=True, force_stage="nonexistent", board=board
        )
        assert result is False

    def test_auto_advances_through_gates(self, tmp_path, monkeypatch):
        board = _setup_project(
            tmp_path, monkeypatch,
            stages={"test": ["echo ok"]},
            pause_at=["test"],
        )
        result = forge.run_project("testproject", "T-001", auto=True, board=board)
        assert result is True

    def test_escalates_after_threshold(self, tmp_path, monkeypatch):
        """After escalation_threshold rollbacks, rollback target escalates upstream."""
        monkeypatch.setattr(forge, "_PROJECTS_DIR", str(tmp_path / "projects"))
        monkeypatch.setattr(forge, "_RUNS_DIR", str(tmp_path / "runs"))

        proj = tmp_path / "projects" / "testproject"
        proj.mkdir(parents=True)
        manifest = _make_manifest(stages={"test": ["exit 1"]})
        (proj / "manifest.yaml").write_text(yaml.dump(manifest), encoding="utf-8")
        gates = {
            "pause_at": [],
            "rollback": {"test": "implement"},
            "escalation_threshold": 1,
        }
        (proj / "gates.yaml").write_text(yaml.dump(gates), encoding="utf-8")

        board = LocalBoard(board_path=str(tmp_path / "board.json"))
        # First failure: rollback_count["test"] reaches threshold → escalate
        board.upsert_ticket("T-001", {"rollback_counts": {"test": 1}})
        forge.run_project("testproject", "T-001", auto=True, board=board)

        ticket = board.get_ticket("T-001")
        # implement is index 4, one step back = research (index 3)
        assert ticket["rollback_to"] == "research"


# ---------------------------------------------------------------------------
# CLI parser
# ---------------------------------------------------------------------------


class TestBuildParser:
    def test_run_subcommand_parsed(self):
        parser = forge.build_parser()
        args = parser.parse_args(["run", "--project", "omnidigest", "--ticket", "T-001"])
        assert args.project == "omnidigest"
        assert args.ticket == "T-001"
        assert args.auto is False

    def test_run_auto_flag(self):
        parser = forge.build_parser()
        args = parser.parse_args(["run", "--project", "p", "--ticket", "T-1", "--auto"])
        assert args.auto is True

    def test_force_stage_flag(self):
        parser = forge.build_parser()
        args = parser.parse_args(
            ["run", "--project", "p", "--ticket", "T-1", "--force-stage", "test"]
        )
        assert args.force_stage == "test"

    def test_status_subcommand_parsed(self):
        parser = forge.build_parser()
        args = parser.parse_args(["status", "--ticket", "T-001"])
        assert args.ticket == "T-001"

    def test_list_subcommand_parsed(self):
        parser = forge.build_parser()
        args = parser.parse_args(["list"])
        assert args.command == "list"

    def test_missing_required_args_exits(self):
        parser = forge.build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["run", "--project", "p"])  # missing --ticket
