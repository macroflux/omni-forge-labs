"""Tests for forge.py — the OmniForge Labs local runner."""

from __future__ import annotations

import argparse
import os
import sys

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


def _stage_cmd(stage: str) -> str:
    """Single-line shell command that echoes and writes the required artifact."""
    artifact = forge.STAGE_ARTIFACTS.get(stage, f"{stage}.md")
    return f'echo "{stage} ok" && echo "# {stage}" > "$FORGE_RUN_DIR/{artifact}"'


def _make_manifest(
    stages: dict | None = None,
    artifact_folders: list | None = None,
    repo_root: str | None = None,
    asserts: dict | None = None,
):
    m: dict = {
        "name": "testproject",
        "description": "Test project",
        "stages": stages or {},
        "artifact_folders": artifact_folders or [],
    }
    if repo_root is not None:
        m["repo_root"] = repo_root
    if asserts is not None:
        m["asserts"] = asserts
    return m


def _make_gates(pause_at=None, rollback=None, escalation_threshold=2):
    return {
        "pause_at": pause_at or [],
        "rollback": rollback or {"test": "implement", "integrate": "implement"},
        "escalation_threshold": escalation_threshold,
    }


def _setup_project(
    tmp_path,
    monkeypatch,
    stages=None,
    pause_at=None,
    rollback=None,
    asserts=None,
):
    """Create a temporary project with manifest + gates; patch forge module paths."""
    monkeypatch.setattr(forge, "_PROJECTS_DIR", str(tmp_path / "projects"))
    monkeypatch.setattr(forge, "_RUNS_DIR", str(tmp_path / "runs"))

    proj = tmp_path / "projects" / "testproject"
    proj.mkdir(parents=True)

    manifest = _make_manifest(
        stages=stages
        or {
            "implement": [_stage_cmd("implement")],
            "test": [_stage_cmd("test")],
        },
        # Absolute path so commands run from tmp_path regardless of _RUNNER_DIR.
        repo_root=str(tmp_path),
        asserts=asserts,
    )
    (proj / "manifest.yaml").write_text(yaml.dump(manifest), encoding="utf-8")

    gates = _make_gates(
        pause_at=pause_at or [],
        rollback=rollback or {"test": "implement"},
    )
    (proj / "gates.yaml").write_text(yaml.dump(gates), encoding="utf-8")

    board = LocalBoard(board_path=str(tmp_path / "board.json"))
    return board


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

    def test_extra_env_is_visible_to_command(self, tmp_path):
        log = str(tmp_path / "test.log")
        rc = forge.run_command(
            "echo $MY_VAR",
            cwd=str(tmp_path),
            log_path=log,
            extra_env={"MY_VAR": "hello_from_env"},
        )
        assert rc == 0
        with open(log, encoding="utf-8") as fh:
            assert "hello_from_env" in fh.read()


# ---------------------------------------------------------------------------
# run_asserts
# ---------------------------------------------------------------------------


class TestRunAsserts:
    def test_file_exists_passes(self, tmp_path):
        target = tmp_path / "output.json"
        target.write_text('{"key": "value"}')
        result = forge.run_asserts(
            [{"type": "file_exists", "path": str(target)}], str(tmp_path)
        )
        assert result is None

    def test_file_exists_fails_when_missing(self, tmp_path):
        result = forge.run_asserts(
            [{"type": "file_exists", "path": str(tmp_path / "missing.json")}],
            str(tmp_path),
        )
        assert result is not None
        assert "file_exists" in result

    def test_json_has_keys_passes(self, tmp_path):
        target = tmp_path / "data.json"
        target.write_text('{"a": 1, "b": 2}')
        result = forge.run_asserts(
            [{"type": "json_has_keys", "path": str(target), "keys": ["a", "b"]}],
            str(tmp_path),
        )
        assert result is None

    def test_json_has_keys_fails_on_missing_key(self, tmp_path):
        target = tmp_path / "data.json"
        target.write_text('{"a": 1}')
        result = forge.run_asserts(
            [{"type": "json_has_keys", "path": str(target), "keys": ["a", "b"]}],
            str(tmp_path),
        )
        assert result is not None
        assert "b" in result

    def test_json_has_keys_fails_on_invalid_json(self, tmp_path):
        target = tmp_path / "bad.json"
        target.write_text("not json")
        result = forge.run_asserts(
            [{"type": "json_has_keys", "path": str(target), "keys": ["a"]}],
            str(tmp_path),
        )
        assert result is not None

    def test_json_has_keys_fails_when_file_missing(self, tmp_path):
        result = forge.run_asserts(
            [{"type": "json_has_keys", "path": str(tmp_path / "gone.json"), "keys": ["a"]}],
            str(tmp_path),
        )
        assert result is not None
        assert "json_has_keys" in result

    def test_unknown_type_returns_error(self, tmp_path):
        result = forge.run_asserts([{"type": "unknown_type"}], str(tmp_path))
        assert result is not None
        assert "Unknown" in result

    def test_empty_asserts_returns_none(self, tmp_path):
        assert forge.run_asserts([], str(tmp_path)) is None


# ---------------------------------------------------------------------------
# run_project — core SDLC
# ---------------------------------------------------------------------------


class TestRunProject:
    def test_delivers_on_all_passing_stages(self, tmp_path, monkeypatch):
        board = _setup_project(tmp_path, monkeypatch)
        result = forge.run_project("testproject", "T-001", auto=True, board=board)
        assert result is True
        ticket = board.get_ticket("T-001")
        assert ticket["status"] == "delivered"

    def test_fails_and_records_rollback_on_bad_command(self, tmp_path, monkeypatch):
        board = _setup_project(
            tmp_path,
            monkeypatch,
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
            tmp_path,
            monkeypatch,
            stages={"implement": [_stage_cmd("implement")], "test": ["exit 1"]},
            rollback={"test": "implement"},
        )
        forge.run_project("testproject", "T-001", auto=True, board=board)
        ticket = board.get_ticket("T-001")
        assert ticket["last_passed_stage"] == "implement"

    def test_skips_stages_with_no_commands(self, tmp_path, monkeypatch):
        """Stages absent from the manifest are silently skipped."""
        board = _setup_project(
            tmp_path,
            monkeypatch,
            stages={"deliver": [_stage_cmd("deliver")]},
        )
        result = forge.run_project("testproject", "T-001", auto=True, board=board)
        assert result is True

    def test_force_stage_skips_earlier_stages(self, tmp_path, monkeypatch):
        """--force-stage skips all stages before the specified one."""
        calls: list[str] = []

        def fake_run_command(cmd, cwd, log_path, extra_env=None):
            calls.append(cmd)
            # Create all artifacts so enforcement passes.
            if extra_env and "FORGE_RUN_DIR" in extra_env:
                run_dir = extra_env["FORGE_RUN_DIR"]
                os.makedirs(run_dir, exist_ok=True)
                for artifact in forge.STAGE_ARTIFACTS.values():
                    p = os.path.join(run_dir, artifact)
                    if not os.path.exists(p):
                        with open(p, "w", encoding="utf-8") as f:
                            f.write("mock artifact\n")
            return 0

        board = _setup_project(
            tmp_path,
            monkeypatch,
            stages={
                "implement": [_stage_cmd("implement")],
                "test": [_stage_cmd("test")],
                "deliver": [_stage_cmd("deliver")],
            },
        )
        monkeypatch.setattr(forge, "run_command", fake_run_command)
        forge.run_project(
            "testproject", "T-001", auto=True, force_stage="test", board=board
        )
        cmds_str = " ".join(calls)
        assert "implement ok" not in cmds_str  # implement was skipped
        assert "test ok" in cmds_str  # test was run

    def test_unknown_force_stage_returns_false(self, tmp_path, monkeypatch):
        board = _setup_project(tmp_path, monkeypatch)
        result = forge.run_project(
            "testproject", "T-001", auto=True, force_stage="nonexistent", board=board
        )
        assert result is False

    def test_auto_advances_through_gates(self, tmp_path, monkeypatch):
        board = _setup_project(
            tmp_path,
            monkeypatch,
            stages={"test": [_stage_cmd("test")]},
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
        # Pre-seed rollback_counts so next failure crosses threshold.
        board.upsert_ticket("T-001", {"rollback_counts": {"test": 1}})
        forge.run_project("testproject", "T-001", auto=True, board=board)

        ticket = board.get_ticket("T-001")
        # implement is index 4, one step back = research (index 3)
        assert ticket["rollback_to"] == "research"

    def test_preserves_approvals_across_runs(self, tmp_path, monkeypatch):
        """Approvals set on the board survive a second run_project call."""
        board = _setup_project(
            tmp_path,
            monkeypatch,
            stages={"test": [_stage_cmd("test")]},
            pause_at=["test"],
        )
        # Seed an approval before running.
        board.upsert_ticket("T-001", {"approvals": {"test": True}})
        result = forge.run_project("testproject", "T-001", auto=False, board=board)
        assert result is True


# ---------------------------------------------------------------------------
# Durable approvals / pause-and-resume
# ---------------------------------------------------------------------------


class TestApproveFlow:
    def test_pauses_at_gate_when_not_approved(self, tmp_path, monkeypatch):
        """Without --auto and no board approval, runner pauses at the gate."""
        board = _setup_project(
            tmp_path,
            monkeypatch,
            stages={
                "implement": [_stage_cmd("implement")],
                "test": [_stage_cmd("test")],
            },
            pause_at=["test"],
        )
        result = forge.run_project("testproject", "T-001", auto=False, board=board)
        assert result is False
        assert board.get_ticket("T-001")["status"] == "paused_at_test"

    def test_paused_ticket_has_history_event(self, tmp_path, monkeypatch):
        board = _setup_project(
            tmp_path,
            monkeypatch,
            stages={"test": [_stage_cmd("test")]},
            pause_at=["test"],
        )
        forge.run_project("testproject", "T-001", auto=False, board=board)
        events = [e["event"] for e in board.get_ticket("T-001").get("history", [])]
        assert "paused" in events

    def test_resumes_after_board_approval(self, tmp_path, monkeypatch):
        """After approval is written to the board, the runner advances past the gate."""
        board = _setup_project(
            tmp_path,
            monkeypatch,
            stages={
                "implement": [_stage_cmd("implement")],
                "test": [_stage_cmd("test")],
            },
            pause_at=["test"],
        )
        # First run: pauses at test gate.
        forge.run_project("testproject", "T-001", auto=False, board=board)
        assert board.get_ticket("T-001")["status"] == "paused_at_test"

        # Approve via board (simulates `forge approve`).
        board.upsert_ticket("T-001", {"approvals": {"test": True}})

        # Second run: should advance past the gate and deliver.
        result = forge.run_project("testproject", "T-001", auto=False, board=board)
        assert result is True
        assert board.get_ticket("T-001")["status"] == "delivered"

    def test_cmd_approve_sets_approval_on_board(self, tmp_path, monkeypatch):
        """forge approve sets approvals[stage]=True and approvals_meta on the board."""
        board = LocalBoard(board_path=str(tmp_path / "board.json"))
        board.upsert_ticket(
            "T-001", {"project": "testproject", "status": "paused_at_design"}
        )
        # Patch LocalBoard() constructor used inside cmd_approve.
        monkeypatch.setattr(
            "adapters.local_board.LocalBoard", lambda board_path=None: board
        )
        monkeypatch.setattr(forge, "_RUNNER_DIR", str(tmp_path))

        args = argparse.Namespace(ticket="T-001", stage="design", by="Chris")
        forge.cmd_approve(args)

        ticket = board.get_ticket("T-001")
        assert ticket["approvals"]["design"] is True
        assert ticket["approvals_meta"]["design"]["by"] == "Chris"

    def test_cmd_approve_without_by_uses_unknown(self, tmp_path, monkeypatch):
        board = LocalBoard(board_path=str(tmp_path / "board.json"))
        board.upsert_ticket("T-001", {"project": "testproject"})
        monkeypatch.setattr(
            "adapters.local_board.LocalBoard", lambda board_path=None: board
        )
        monkeypatch.setattr(forge, "_RUNNER_DIR", str(tmp_path))

        args = argparse.Namespace(ticket="T-001", stage="design", by=None)
        forge.cmd_approve(args)

        ticket = board.get_ticket("T-001")
        assert ticket["approvals"]["design"] is True
        assert ticket["approvals_meta"]["design"]["by"] == "unknown"

    def test_approve_appends_history_event(self, tmp_path, monkeypatch):
        board = LocalBoard(board_path=str(tmp_path / "board.json"))
        board.upsert_ticket("T-001", {"project": "testproject"})
        monkeypatch.setattr(
            "adapters.local_board.LocalBoard", lambda board_path=None: board
        )
        monkeypatch.setattr(forge, "_RUNNER_DIR", str(tmp_path))

        args = argparse.Namespace(ticket="T-001", stage="design", by="Alice")
        forge.cmd_approve(args)

        # approve_stage stores events with "type" key
        event_types = [e.get("type") for e in board.get_ticket("T-001").get("history", [])]
        assert "approved" in event_types


# ---------------------------------------------------------------------------
# Artifact enforcement
# ---------------------------------------------------------------------------


class TestArtifactEnforcement:
    def test_fails_when_artifact_missing(self, tmp_path, monkeypatch):
        """Stage fails when its required .md artifact is absent from run_dir."""
        board = _setup_project(
            tmp_path,
            monkeypatch,
            stages={"implement": ["echo impl"]},  # does NOT create artifact
        )
        result = forge.run_project("testproject", "T-001", auto=True, board=board)
        assert result is False
        ticket = board.get_ticket("T-001")
        assert ticket["status"] == "failed_at_implement"
        failure = next(
            (e for e in ticket.get("history", []) if e.get("event") == "stage_failed"),
            None,
        )
        assert failure is not None
        assert "implementation.md" in failure["reason"]

    def test_passes_when_artifact_exists(self, tmp_path, monkeypatch):
        """Stage passes when the required artifact is created by the command."""
        board = _setup_project(
            tmp_path,
            monkeypatch,
            stages={
                "implement": [_stage_cmd("implement")],
                "test": [_stage_cmd("test")],
            },
        )
        result = forge.run_project("testproject", "T-001", auto=True, board=board)
        assert result is True

    def test_correct_artifact_name_per_stage(self, tmp_path, monkeypatch):
        """implement stage expects implementation.md, test expects test_report.md."""
        assert forge.STAGE_ARTIFACTS["implement"] == "implementation.md"
        assert forge.STAGE_ARTIFACTS["test"] == "test_report.md"
        assert forge.STAGE_ARTIFACTS["integrate"] == "integration_report.md"
        assert forge.STAGE_ARTIFACTS["deliver"] == "delivery.md"


# ---------------------------------------------------------------------------
# Assertions in manifest
# ---------------------------------------------------------------------------


class TestManifestAsserts:
    def test_file_exists_assert_passes(self, tmp_path, monkeypatch):
        target = tmp_path / "output.txt"
        target.write_text("ok")
        board = _setup_project(
            tmp_path,
            monkeypatch,
            stages={"deliver": [_stage_cmd("deliver")]},
            asserts={"deliver": [{"type": "file_exists", "path": str(target)}]},
        )
        result = forge.run_project("testproject", "T-001", auto=True, board=board)
        assert result is True

    def test_file_exists_assert_fails(self, tmp_path, monkeypatch):
        board = _setup_project(
            tmp_path,
            monkeypatch,
            stages={"deliver": [_stage_cmd("deliver")]},
            asserts={
                "deliver": [
                    {"type": "file_exists", "path": str(tmp_path / "missing.txt")}
                ]
            },
        )
        result = forge.run_project("testproject", "T-001", auto=True, board=board)
        assert result is False
        ticket = board.get_ticket("T-001")
        assert ticket["status"] == "failed_at_deliver"
        failure = next(
            (e for e in ticket.get("history", []) if e.get("event") == "stage_failed"),
            None,
        )
        assert failure is not None
        assert "assertion failed" in failure["reason"]

    def test_json_has_keys_assert_passes(self, tmp_path, monkeypatch):
        target = tmp_path / "digest.json"
        target.write_text('{"generated_at": "2026", "categories": []}')
        board = _setup_project(
            tmp_path,
            monkeypatch,
            stages={"deliver": [_stage_cmd("deliver")]},
            asserts={
                "deliver": [
                    {
                        "type": "json_has_keys",
                        "path": str(target),
                        "keys": ["generated_at", "categories"],
                    }
                ]
            },
        )
        result = forge.run_project("testproject", "T-001", auto=True, board=board)
        assert result is True

    def test_json_has_keys_assert_fails_on_missing_key(self, tmp_path, monkeypatch):
        target = tmp_path / "digest.json"
        target.write_text('{"generated_at": "2026"}')
        board = _setup_project(
            tmp_path,
            monkeypatch,
            stages={"deliver": [_stage_cmd("deliver")]},
            asserts={
                "deliver": [
                    {
                        "type": "json_has_keys",
                        "path": str(target),
                        "keys": ["generated_at", "categories"],
                    }
                ]
            },
        )
        result = forge.run_project("testproject", "T-001", auto=True, board=board)
        assert result is False


# ---------------------------------------------------------------------------
# Run report
# ---------------------------------------------------------------------------


class TestRunReport:
    def test_written_on_delivery(self, tmp_path, monkeypatch):
        board = _setup_project(tmp_path, monkeypatch)
        forge.run_project("testproject", "T-001", auto=True, board=board)
        run_dir = board.get_ticket("T-001")["run_dir"]
        report = os.path.join(run_dir, "run_report.md")
        assert os.path.exists(report)
        with open(report, encoding="utf-8") as fh:
            content = fh.read()
        assert "Delivered" in content
        assert "T-001" in content

    def test_written_on_pause(self, tmp_path, monkeypatch):
        board = _setup_project(
            tmp_path,
            monkeypatch,
            stages={"test": [_stage_cmd("test")]},
            pause_at=["test"],
        )
        forge.run_project("testproject", "T-001", auto=False, board=board)
        run_dir = board.get_ticket("T-001")["run_dir"]
        report = os.path.join(run_dir, "run_report.md")
        assert os.path.exists(report)
        with open(report, encoding="utf-8") as fh:
            content = fh.read()
        assert "Paused at" in content
        assert "approve" in content

    def test_written_on_failure(self, tmp_path, monkeypatch):
        board = _setup_project(
            tmp_path,
            monkeypatch,
            stages={"implement": ["exit 1"]},
            rollback={"implement": "design"},
        )
        forge.run_project("testproject", "T-001", auto=True, board=board)
        run_dir = board.get_ticket("T-001")["run_dir"]
        report = os.path.join(run_dir, "run_report.md")
        assert os.path.exists(report)
        with open(report, encoding="utf-8") as fh:
            content = fh.read()
        assert "Rollback" in content
        assert "design" in content

    def test_stage_results_in_report(self, tmp_path, monkeypatch):
        board = _setup_project(tmp_path, monkeypatch)
        forge.run_project("testproject", "T-001", auto=True, board=board)
        run_dir = board.get_ticket("T-001")["run_dir"]
        with open(os.path.join(run_dir, "run_report.md"), encoding="utf-8") as fh:
            content = fh.read()
        assert "PASS" in content
        assert "implement" in content


# ---------------------------------------------------------------------------
# Board history
# ---------------------------------------------------------------------------


class TestBoardHistory:
    def test_history_on_delivery(self, tmp_path, monkeypatch):
        board = _setup_project(tmp_path, monkeypatch)
        forge.run_project("testproject", "T-001", auto=True, board=board)
        ticket = board.get_ticket("T-001")
        events = [e["event"] for e in ticket.get("history", [])]
        assert "run_started" in events
        assert "stage_passed" in events
        assert "delivered" in events

    def test_history_records_stage_names(self, tmp_path, monkeypatch):
        board = _setup_project(tmp_path, monkeypatch)
        forge.run_project("testproject", "T-001", auto=True, board=board)
        ticket = board.get_ticket("T-001")
        passed_stages = [
            e["stage"]
            for e in ticket.get("history", [])
            if e.get("event") == "stage_passed"
        ]
        assert "implement" in passed_stages
        assert "test" in passed_stages

    def test_history_records_failure(self, tmp_path, monkeypatch):
        board = _setup_project(
            tmp_path,
            monkeypatch,
            stages={"implement": ["exit 1"]},
        )
        forge.run_project("testproject", "T-001", auto=True, board=board)
        ticket = board.get_ticket("T-001")
        failures = [
            e for e in ticket.get("history", []) if e.get("event") == "stage_failed"
        ]
        assert len(failures) == 1
        assert failures[0]["stage"] == "implement"


# ---------------------------------------------------------------------------
# Repo root + per-command cwd
# ---------------------------------------------------------------------------


class TestRepoCwd:
    def test_repo_root_sets_resolved_cwd(self, tmp_path, monkeypatch):
        """Commands run from repo_root when it is set in the manifest."""
        cwd_seen: list[str] = []

        def fake_run_command(cmd, cwd, log_path, extra_env=None):
            cwd_seen.append(cwd)
            if extra_env and "FORGE_RUN_DIR" in extra_env:
                run_dir = extra_env["FORGE_RUN_DIR"]
                os.makedirs(run_dir, exist_ok=True)
                for artifact in forge.STAGE_ARTIFACTS.values():
                    p = os.path.join(run_dir, artifact)
                    if not os.path.exists(p):
                        with open(p, "w", encoding="utf-8") as f:
                            f.write("mock\n")
            return 0

        board = _setup_project(
            tmp_path,
            monkeypatch,
            stages={"implement": ["echo hello"]},
        )
        # _setup_project already sets repo_root=str(tmp_path) in the manifest.
        monkeypatch.setattr(forge, "run_command", fake_run_command)
        forge.run_project("testproject", "T-001", auto=True, board=board)
        assert any(str(tmp_path) in c for c in cwd_seen)

    def test_per_command_cwd_override(self, tmp_path, monkeypatch):
        """A dict command entry with cwd runs in that subdirectory."""
        subdir = tmp_path / "sub"
        subdir.mkdir()
        cwd_seen: list[str] = []

        def fake_run_command(cmd, cwd, log_path, extra_env=None):
            cwd_seen.append(cwd)
            if extra_env and "FORGE_RUN_DIR" in extra_env:
                run_dir = extra_env["FORGE_RUN_DIR"]
                os.makedirs(run_dir, exist_ok=True)
                for artifact in forge.STAGE_ARTIFACTS.values():
                    p = os.path.join(run_dir, artifact)
                    if not os.path.exists(p):
                        with open(p, "w", encoding="utf-8") as f:
                            f.write("mock\n")
            return 0

        monkeypatch.setattr(forge, "_PROJECTS_DIR", str(tmp_path / "projects"))
        monkeypatch.setattr(forge, "_RUNS_DIR", str(tmp_path / "runs"))
        proj = tmp_path / "projects" / "testproject"
        proj.mkdir(parents=True)
        # Use a dict command entry with explicit cwd override (absolute path).
        manifest = _make_manifest(
            stages={"implement": [{"cmd": "echo hi", "cwd": str(subdir)}]},
            repo_root=str(tmp_path),
        )
        (proj / "manifest.yaml").write_text(yaml.dump(manifest), encoding="utf-8")
        gates = _make_gates()
        (proj / "gates.yaml").write_text(yaml.dump(gates), encoding="utf-8")

        board = LocalBoard(board_path=str(tmp_path / "board.json"))
        monkeypatch.setattr(forge, "run_command", fake_run_command)
        forge.run_project("testproject", "T-001", auto=True, board=board)
        assert str(subdir) in cwd_seen


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

    def test_approve_subcommand_parsed(self):
        parser = forge.build_parser()
        args = parser.parse_args(
            ["approve", "--ticket", "T-001", "--stage", "design"]
        )
        assert args.ticket == "T-001"
        assert args.stage == "design"
        assert args.by is None

    def test_approve_subcommand_with_by(self):
        parser = forge.build_parser()
        args = parser.parse_args(
            ["approve", "--ticket", "T-001", "--stage", "design", "--by", "Chris"]
        )
        assert args.by == "Chris"

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
