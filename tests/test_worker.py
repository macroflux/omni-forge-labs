"""Tests for the unattended worker loop (omniforge/viewer/worker.py)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

import pytest

# Import the public helpers directly from worker module
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "omniforge", "viewer"))
from worker import (  # type: ignore
    _is_runnable,
    _next_ticket,
    _forge_cmd,
    _read_state,
    _write_state,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def state_dir(tmp_path, monkeypatch):
    """Point WORKER_STATE at a temporary file."""
    import worker as w
    monkeypatch.setattr(w, "WORKER_STATE", tmp_path / "worker.state.json")
    monkeypatch.setattr(w, "RUNS_DIR", tmp_path)
    return tmp_path


# ---------------------------------------------------------------------------
# _is_runnable
# ---------------------------------------------------------------------------

class TestIsRunnable:
    def _t(self, status: str, extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return {"ticket_id": "T-001", "status": status, **(extra or {})}

    def test_created_is_runnable(self):
        assert _is_runnable(self._t("created")) is True

    def test_pending_is_runnable(self):
        assert _is_runnable(self._t("pending")) is True

    def test_failed_at_with_rollback_is_runnable(self):
        assert _is_runnable(self._t("failed_at_test", {"rollback_to": "implement"})) is True

    def test_failed_at_without_rollback_is_runnable(self):
        # failed_at_* with no rollback_to is still considered runnable;
        # forge itself will handle the missing flag gracefully
        assert _is_runnable(self._t("failed_at_integrate")) is True

    def test_running_is_not_runnable(self):
        assert _is_runnable(self._t("running")) is False

    def test_paused_at_is_not_runnable(self):
        assert _is_runnable(self._t("paused_at_design")) is False

    def test_delivered_is_not_runnable(self):
        assert _is_runnable(self._t("delivered")) is False

    def test_empty_status_is_not_runnable(self):
        assert _is_runnable({"ticket_id": "T-001", "status": ""}) is False

    def test_missing_status_is_not_runnable(self):
        assert _is_runnable({"ticket_id": "T-001"}) is False


# ---------------------------------------------------------------------------
# _next_ticket
# ---------------------------------------------------------------------------

class TestNextTicket:
    def test_returns_none_for_empty_board(self):
        assert _next_ticket({}) is None

    def test_returns_none_when_all_skipped(self):
        board = {
            "T-001": {"ticket_id": "T-001", "status": "delivered"},
            "T-002": {"ticket_id": "T-002", "status": "running"},
            "T-003": {"ticket_id": "T-003", "status": "paused_at_design"},
        }
        assert _next_ticket(board) is None

    def test_returns_first_runnable(self):
        board = {
            "T-001": {"ticket_id": "T-001", "status": "delivered"},
            "T-002": {"ticket_id": "T-002", "status": "created"},
            "T-003": {"ticket_id": "T-003", "status": "pending"},
        }
        result = _next_ticket(board)
        assert result is not None
        assert result["status"] in ("created", "pending")

    def test_skips_paused_returns_next(self):
        board = {
            "T-001": {"ticket_id": "T-001", "status": "paused_at_test"},
            "T-002": {"ticket_id": "T-002", "status": "pending"},
        }
        result = _next_ticket(board)
        assert result is not None
        assert result["ticket_id"] == "T-002"


# ---------------------------------------------------------------------------
# _forge_cmd
# ---------------------------------------------------------------------------

class TestForgeCmd:
    def _ticket(self, status: str = "created", rollback_to: Optional[str] = None) -> Dict[str, Any]:
        t: Dict[str, Any] = {
            "ticket_id": "T-001",
            "project": "omnidigest",
            "status": status,
        }
        if rollback_to:
            t["rollback_to"] = rollback_to
        return t

    def test_basic_run_command(self):
        cmd = _forge_cmd(self._ticket())
        assert "forge.py" in " ".join(cmd)
        assert "--project" in cmd
        assert "omnidigest" in cmd
        assert "--ticket" in cmd
        assert "T-001" in cmd

    def test_no_force_stage_for_fresh_ticket(self):
        cmd = _forge_cmd(self._ticket(status="created"))
        assert "--force-stage" not in cmd

    def test_force_stage_for_failed_with_rollback(self):
        cmd = _forge_cmd(self._ticket(status="failed_at_test", rollback_to="implement"))
        assert "--force-stage" in cmd
        idx = cmd.index("--force-stage")
        assert cmd[idx + 1] == "implement"

    def test_no_force_stage_for_failed_without_rollback(self):
        cmd = _forge_cmd(self._ticket(status="failed_at_test"))
        assert "--force-stage" not in cmd


# ---------------------------------------------------------------------------
# _read_state / _write_state
# ---------------------------------------------------------------------------

class TestStateIO:
    def test_read_state_returns_empty_dict_when_missing(self, state_dir):
        # WORKER_STATE doesn't exist yet
        result = _read_state()
        assert result == {}

    def test_write_then_read_round_trips(self, state_dir):
        _write_state({"running": True, "pid": 12345})
        state = _read_state()
        assert state["running"] is True
        assert state["pid"] == 12345

    def test_write_creates_file(self, state_dir):
        import worker as w
        assert not w.WORKER_STATE.exists()
        _write_state({"running": False})
        assert w.WORKER_STATE.exists()
