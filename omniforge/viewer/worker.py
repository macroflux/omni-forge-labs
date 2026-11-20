#!/usr/bin/env python3
"""Unattended worker loop for OmniForge.

Processes one ticket at a time, skipping gated/held/unready tickets.
All activity is appended to runs/worker.log.

Lifecycle
---------
- Started by Flask via ``POST /worker/start`` as a detached subprocess.
- Stopped by Flask via ``POST /worker/stop``, which sets ``running=false``
  in ``runs/worker.state.json``.  The loop checks this file each iteration.
- Tickets are processed in board insertion order.  Runnable means status is
  ``created``, ``pending``, or ``failed_at_*`` (with a ``rollback_to`` set).
  Gated (``paused_at_*``), ``running``, and ``delivered`` tickets are skipped.
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
RUNS_DIR = REPO_ROOT / "runs"
BOARD_PATH = RUNS_DIR / "board.json"
WORKER_LOG = RUNS_DIR / "worker.log"
WORKER_STATE = RUNS_DIR / "worker.state.json"

POLL_INTERVAL = 5  # seconds to sleep when no runnable ticket is found


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def _setup_logging() -> None:
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    fmt = "%(asctime)s [%(levelname)s] %(message)s"
    logging.basicConfig(
        level=logging.INFO,
        format=fmt,
        handlers=[
            logging.FileHandler(str(WORKER_LOG), encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )


# ---------------------------------------------------------------------------
# Helpers: timestamps, state I/O
# ---------------------------------------------------------------------------

def _now() -> str:
    return datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%S")


def _read_state() -> Dict[str, Any]:
    try:
        return json.loads(WORKER_STATE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write_state(state: Dict[str, Any]) -> None:
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    WORKER_STATE.write_text(json.dumps(state, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# Helpers: board
# ---------------------------------------------------------------------------

def _read_board() -> Dict[str, Any]:
    try:
        from omniforge.runner.adapters.local_board import LocalBoard
        return LocalBoard(str(BOARD_PATH)).list_tickets()
    except Exception:
        return {}


def _is_runnable(ticket: Dict[str, Any]) -> bool:
    """Return True if the worker should process this ticket.

    Skipped statuses
    ----------------
    - ``running``     — already being executed
    - ``paused_at_*`` — waiting for human gate approval
    - ``delivered``   — completed successfully

    Runnable statuses
    -----------------
    - ``created``, ``pending`` — fresh tickets
    - ``failed_at_*``          — need a retry from ``rollback_to``
    """
    status = (ticket.get("status") or "").lower()
    if not status:
        return False
    if status.startswith("running"):
        return False
    if status.startswith("paused"):
        return False
    if status == "delivered":
        return False
    if status in ('created', 'pending'):
        return True
    return status.startswith('failed_at_') and bool(ticket.get('rollback_to')) and sum(ticket.get('rollback_counts', {}).values()) < 3


def _next_ticket(board: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Return the first runnable ticket from the board, or None."""
    for ticket in board.values():
        if _is_runnable(ticket):
            return ticket
    return None


# ---------------------------------------------------------------------------
# Helpers: subprocess
# ---------------------------------------------------------------------------

def _repo_python() -> str:
    return os.environ.get("PYTHON", "") or os.path.abspath(sys.executable)


def _forge_cmd(ticket: Dict[str, Any]) -> List[str]:
    """Build the forge.py run command for *ticket*."""
    project = ticket.get("project", "")
    ticket_id = ticket.get("ticket_id", "")
    status = (ticket.get("status") or "").lower()

    cmd = [
        _repo_python(),
        str(REPO_ROOT / "omniforge" / "runner" / "forge.py"),
        "run",
        "--project", project,
        "--ticket", ticket_id,
    ]

    # The runner resolves normal resume points and invalidates stale workspace approvals.

    return cmd


def _worker_env() -> Dict[str, str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(REPO_ROOT / "omniforge" / "runner")
    return env


# ---------------------------------------------------------------------------
# Core: run one ticket
# ---------------------------------------------------------------------------

def _run_ticket(ticket: Dict[str, Any]) -> None:
    ticket_id = ticket.get("ticket_id", "unknown")
    project = ticket.get("project", "unknown")
    status = ticket.get("status", "unknown")
    logging.info(
        "Picking up ticket %s (project=%s, status=%s)", ticket_id, project, status
    )

    cmd = _forge_cmd(ticket)
    logging.info("Command: %s", " ".join(cmd))

    proc = subprocess.run(
        cmd,
        cwd=str(REPO_ROOT),
        env=_worker_env(),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding='utf-8', errors='replace',
    )

    for line in (proc.stdout or "").splitlines():
        logging.info("  [%s] %s", ticket_id, line)

    if proc.returncode == 0:
        logging.info("Ticket %s run completed (exit 0)", ticket_id)
    else:
        logging.warning(
            "Ticket %s run finished with exit code %d", ticket_id, proc.returncode
        )


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def main() -> None:
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    _setup_logging()

    pid = os.getpid()
    _write_state({"running": True, "pid": pid, "started_at": _now()})
    logging.info("Worker started (PID %d)", pid)

    try:
        while True:
            state = _read_state()
            if not state.get("running", True):
                logging.info("Received stop signal via state file")
                break

            _write_state({**state, "last_tick": _now()})

            board = _read_board()
            ticket = _next_ticket(board)

            if ticket:
                _run_ticket(ticket)
                # Brief pause before polling again after a completed run
                time.sleep(1)
            else:
                logging.debug("No runnable tickets; sleeping %ds", POLL_INTERVAL)
                time.sleep(POLL_INTERVAL)

    except KeyboardInterrupt:
        logging.info("Worker interrupted by KeyboardInterrupt")
    finally:
        _write_state({"running": False, "pid": None, "stopped_at": _now()})
        logging.info("Worker stopped")


if __name__ == "__main__":
    main()
