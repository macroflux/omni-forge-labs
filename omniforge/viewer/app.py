#!/usr/bin/env python3
from __future__ import annotations

import difflib
import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from flask import Flask, abort, jsonify, redirect, render_template, request, url_for
from markupsafe import escape as html_escape

# Reuse your board adapter (JSON)
# This file assumes you're running from repo root and PYTHONPATH includes omniforge/runner
from omniforge.runner.adapters.local_board import LocalBoard  # type: ignore

app = Flask(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]  # .../omniforge/viewer -> repo root
RUNS_DIR = REPO_ROOT / "runs"
BOARD_PATH = RUNS_DIR / "board.json"
WORK_DIR = RUNS_DIR / "work"

# Stage workspace files (editable before run)
STAGE_FILES = {
    "intake": "intake.md",
    "plan": "plan.md",
    "design": "design.md",
    "research": "research.md",
}

# Playbooks (read-only reference)
PLAYBOOKS = {
    "sdlc_stages": "omniforge/playbooks/sdlc_stages.md",
    "rollback_rules": "omniforge/playbooks/rollback_rules.md",
    "company_charter": "omniforge/charter/company_charter.md",
}

WORKER_LOG = RUNS_DIR / "worker.log"
WORKER_STATE = RUNS_DIR / "worker.state.json"

SAFE_SEGMENT = re.compile(r"^[A-Za-z0-9_\-\.]+$")


def _safe(seg: str) -> bool:
    return bool(SAFE_SEGMENT.match(seg))


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return f"[error reading file: {e}]"


def _now_ts() -> str:
    return datetime.utcnow().strftime("%Y%m%dT%H%M%S")


def _repo_python() -> str:
    """Use the same python that started Flask."""
    return os.environ.get("PYTHON", "") or os.path.abspath(sys.executable)


def _forge_cmd(project: str, ticket_id: str, auto: bool = False, force_stage: Optional[str] = None) -> List[str]:
    cmd = [
        _repo_python(),
        str(REPO_ROOT / "omniforge" / "runner" / "forge.py"),
        "run",
        "--project",
        project,
        "--ticket",
        ticket_id,
    ]
    if auto:
        cmd.append("--auto")
    if force_stage:
        cmd += ["--force-stage", force_stage]
    return cmd


def _list_projects() -> List[str]:
    """List available projects from omniforge/projects/."""
    projects_dir = REPO_ROOT / "omniforge" / "projects"
    if not projects_dir.exists():
        return []
    return sorted([p.name for p in projects_dir.iterdir() if p.is_dir() and (p / "manifest.yaml").exists()])


def _ticket_work_dir(ticket_id: str) -> Path:
    """Return the workspace directory for a ticket."""
    return WORK_DIR / ticket_id


def _load_workspace(ticket_id: str) -> Dict[str, str]:
    """Load all workspace files for a ticket."""
    work_dir = _ticket_work_dir(ticket_id)
    workspace: Dict[str, str] = {}
    for stage, filename in STAGE_FILES.items():
        fpath = work_dir / filename
        if fpath.exists():
            workspace[stage] = _read_text(fpath)
        else:
            workspace[stage] = ""
    return workspace


def _save_workspace_file(ticket_id: str, stage: str, content: str) -> bool:
    """Save a workspace file for a ticket/stage."""
    if stage not in STAGE_FILES:
        return False
    work_dir = _ticket_work_dir(ticket_id)
    work_dir.mkdir(parents=True, exist_ok=True)
    fpath = work_dir / STAGE_FILES[stage]
    try:
        fpath.write_text(content, encoding="utf-8")
        return True
    except Exception:
        return False


def _list_runs(ticket_id: str) -> Dict[str, Dict[str, Any]]:
    """Return dict of run_ts -> {run_dir, has_report, stages{stage: {log, artifacts[]}}}"""
    ticket_dir = RUNS_DIR / ticket_id
    if not ticket_dir.exists():
        return {}

    runs: Dict[str, Dict[str, Any]] = {}
    for run_dir in sorted([p for p in ticket_dir.iterdir() if p.is_dir()], reverse=True):
        ts = run_dir.name
        report = run_dir / "run_report.md"
        stages: Dict[str, Any] = {}
        for stage_dir in sorted([p for p in run_dir.iterdir() if p.is_dir()]):
            stage = stage_dir.name
            log = stage_dir / "stage.log"
            artifacts = sorted([p.name for p in stage_dir.glob("*.md") if p.name != "run_report.md"])
            stages[stage] = {
                "has_log": log.exists(),
                "artifacts": artifacts,
            }

        runs[ts] = {
            "run_dir": str(run_dir),
            "has_report": report.exists(),
            "stages": stages,
        }

    return runs


def _load_board() -> Tuple[LocalBoard, Dict[str, Any]]:
    board = LocalBoard(board_path=str(BOARD_PATH))
    return board, board.list_tickets() or {}


@app.get("/")
def index():
    _, tickets = _load_board()
    # sort: delivered last, running/failed first (simple priority)
    def pri(t: Dict[str, Any]) -> int:
        s = (t.get("status") or "").lower()
        if s.startswith("running"):
            return 0
        if s.startswith("failed"):
            return 1
        if s.startswith("paused"):
            return 2
        if s.startswith("delivered"):
            return 3
        return 9

    rows = sorted(
        [{"ticket_id": tid, **data} for tid, data in tickets.items()],
        key=lambda r: (pri(r), r.get("ticket_id", "")),
    )
    return render_template("index.html", tickets=rows)


@app.get("/ticket/<ticket_id>")
def ticket(ticket_id: str):
    if not _safe(ticket_id):
        abort(400)

    board, tickets = _load_board()
    t = tickets.get(ticket_id)
    if not t:
        abort(404)

    runs = _list_runs(ticket_id)
    workspace = _load_workspace(ticket_id)
    return render_template(
        "ticket.html",
        ticket=t,
        ticket_id=ticket_id,
        runs=runs,
        workspace=workspace,
        stage_files=STAGE_FILES,
        playbooks=PLAYBOOKS,
    )


@app.get("/ticket/<ticket_id>/run/<run_ts>")
def run_detail(ticket_id: str, run_ts: str):
    if not (_safe(ticket_id) and _safe(run_ts)):
        abort(400)

    run_dir = RUNS_DIR / ticket_id / run_ts
    if not run_dir.exists():
        abort(404)

    report_path = run_dir / "run_report.md"
    report = _read_text(report_path) if report_path.exists() else None

    stages = []
    for stage_dir in sorted([p for p in run_dir.iterdir() if p.is_dir()]):
        stage = stage_dir.name
        log_path = stage_dir / "stage.log"
        artifacts = sorted([p.name for p in stage_dir.glob("*.md")])
        stages.append(
            {
                "stage": stage,
                "has_log": log_path.exists(),
                "artifacts": artifacts,
            }
        )

    return render_template(
        "run.html",
        ticket_id=ticket_id,
        run_ts=run_ts,
        report=report,
        stages=stages,
    )


@app.get("/ticket/<ticket_id>/run/<run_ts>/stage/<stage>/log")
def stage_log(ticket_id: str, run_ts: str, stage: str):
    if not (_safe(ticket_id) and _safe(run_ts) and _safe(stage)):
        abort(400)

    log_path = RUNS_DIR / ticket_id / run_ts / stage / "stage.log"
    if not log_path.exists():
        abort(404)

    content = _read_text(log_path)
    # show tail by default
    tail = int(request.args.get("tail", "400"))
    lines = content.splitlines()
    content = "\n".join(lines[-tail:]) if tail > 0 else content
    return f"<pre style='white-space:pre-wrap'>{html_escape(content)}</pre>"


@app.get("/ticket/<ticket_id>/run/<run_ts>/stage/<stage>/artifact/<name>")
def stage_artifact(ticket_id: str, run_ts: str, stage: str, name: str):
    if not (_safe(ticket_id) and _safe(run_ts) and _safe(stage) and _safe(name)):
        abort(400)

    p = RUNS_DIR / ticket_id / run_ts / stage / name
    if not p.exists():
        abort(404)

    content = _read_text(p)
    return f"<pre style='white-space:pre-wrap'>{html_escape(content)}</pre>"


@app.post("/ticket/<ticket_id>/approve")
def approve(ticket_id: str):
    if not _safe(ticket_id):
        abort(400)

    stage = (request.form.get("stage") or "").strip()
    by = (request.form.get("by") or "").strip() or "client"
    if stage and _safe(stage):
        board = LocalBoard(board_path=str(BOARD_PATH))
        board.approve_stage(ticket_id, stage, by=by)
    return redirect(url_for("ticket", ticket_id=ticket_id))


# ---------------------------------------------------------------------------
# Workspace: Save stage document
# ---------------------------------------------------------------------------
@app.post("/ticket/<ticket_id>/workspace/save")
def save_workspace(ticket_id: str):
    if not _safe(ticket_id):
        abort(400)

    stage = (request.form.get("stage") or "").strip()
    content = request.form.get("content") or ""

    if not stage or stage not in STAGE_FILES:
        abort(400)

    if _save_workspace_file(ticket_id, stage, content):
        return redirect(url_for("ticket", ticket_id=ticket_id) + f"#workspace-{stage}")
    else:
        abort(500)


# ---------------------------------------------------------------------------
# Workspace: API to get workspace content (JSON)
# ---------------------------------------------------------------------------
@app.get("/api/ticket/<ticket_id>/workspace")
def api_workspace(ticket_id: str):
    if not _safe(ticket_id):
        abort(400)
    workspace = _load_workspace(ticket_id)
    return jsonify({"ok": True, "workspace": workspace})


# ---------------------------------------------------------------------------
# Playbooks: Read-only reference documents
# ---------------------------------------------------------------------------
@app.get("/playbook/<name>")
def playbook(name: str):
    if name not in PLAYBOOKS:
        abort(404)
    fpath = REPO_ROOT / PLAYBOOKS[name]
    if not fpath.exists():
        abort(404)
    content = _read_text(fpath)
    return render_template("playbook.html", name=name, content=content)


# ---------------------------------------------------------------------------
# Create Ticket
# ---------------------------------------------------------------------------
@app.post("/ticket/create")
def create_ticket():
    project = (request.form.get("project") or "").strip()
    if not _safe(project):
        abort(400)

    # Allow user to provide ticket id, otherwise generate one
    ticket_id = (request.form.get("ticket_id") or "").strip()
    if ticket_id:
        if not _safe(ticket_id):
            abort(400)
    else:
        ticket_id = f"T-{_now_ts()}"

    board = LocalBoard(board_path=str(BOARD_PATH))
    existing = board.get_ticket(ticket_id)
    if existing:
        # already exists; just go to it
        return redirect(url_for("ticket", ticket_id=ticket_id))

    board.upsert_ticket(ticket_id, {
        "ticket_id": ticket_id,
        "project": project,
        "status": "created",
        "stage": "intake",
        "approvals": {},
        "approvals_meta": {},
        "rollback_counts": {},
        "history": [{"event": "created", "timestamp": _now_ts(), "project": project}],
    })
    # Create workspace directory for immediate editing
    work_dir = _ticket_work_dir(ticket_id)
    work_dir.mkdir(parents=True, exist_ok=True)

    # Seed workspace from project templates if they exist
    templates_dir = REPO_ROOT / "omniforge" / "projects" / project / "templates"
    if templates_dir.exists():
        for stage, filename in STAGE_FILES.items():
            template_src = templates_dir / filename
            workspace_dst = work_dir / filename
            if template_src.exists() and not workspace_dst.exists():
                try:
                    workspace_dst.write_text(template_src.read_text(encoding="utf-8"), encoding="utf-8")
                except Exception:
                    pass  # Silently skip on error

    return redirect(url_for("ticket", ticket_id=ticket_id))


# ---------------------------------------------------------------------------
# Run Ticket (non-blocking subprocess)
# ---------------------------------------------------------------------------
@app.post("/ticket/<ticket_id>/run")
def run_ticket(ticket_id: str):
    if not _safe(ticket_id):
        abort(400)
    auto = request.form.get("auto") == "on"
    force_stage = (request.form.get("force_stage") or "").strip() or None
    if force_stage and not _safe(force_stage):
        abort(400)

    board = LocalBoard(board_path=str(BOARD_PATH))
    t = board.get_ticket(ticket_id)
    if not t:
        abort(404)

    # Prevent double-run: if already running, just redirect
    status = (t.get("status") or "").lower()
    if status.startswith("running"):
        return redirect(url_for("ticket", ticket_id=ticket_id))

    project = t.get("project")
    if not project:
        abort(400)

    # Set status to running immediately (before spawn) to prevent race conditions
    existing = board.get_ticket(ticket_id) or {}
    hist = list(existing.get("history") or [])
    hist.append({"event": "run_requested", "timestamp": _now_ts(), "auto": auto, "force_stage": force_stage})
    board.upsert_ticket(ticket_id, {"status": "running", "stage": None, "history": hist})

    # Spawn Forge as a detached process (MVP). Logs will appear in runs/.
    env = os.environ.copy()
    # forge.py imports from adapters.local_board, so runner dir must be on PYTHONPATH
    env["PYTHONPATH"] = str(REPO_ROOT / "omniforge" / "runner")
    cmd = _forge_cmd(project, ticket_id, auto=auto, force_stage=force_stage)

    subprocess.Popen(
        cmd,
        cwd=str(REPO_ROOT),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
    )

    return redirect(url_for("ticket", ticket_id=ticket_id))


# ---------------------------------------------------------------------------
# Live Tail API (JSON for polling)
# ---------------------------------------------------------------------------
@app.get("/api/ticket/<ticket_id>/run/<run_ts>/stage/<stage>/tail")
def api_tail(ticket_id: str, run_ts: str, stage: str):
    if not (_safe(ticket_id) and _safe(run_ts) and _safe(stage)):
        abort(400)

    log_path = RUNS_DIR / ticket_id / run_ts / stage / "stage.log"
    if not log_path.exists():
        return jsonify({"ok": True, "lines": [], "missing": True})

    tail = int(request.args.get("tail", "120"))
    content = _read_text(log_path)
    lines = content.splitlines()[-tail:]
    return jsonify({"ok": True, "lines": lines, "missing": False})


# ---------------------------------------------------------------------------
# Workspace vs Last Run Diff (compare current workspace to last run artifact)
# ---------------------------------------------------------------------------
@app.get("/ticket/<ticket_id>/workspace-diff")
def workspace_diff(ticket_id: str):
    if not _safe(ticket_id):
        abort(400)

    stage = (request.args.get("stage") or "").strip()
    runs = _list_runs(ticket_id)
    run_timestamps = list(runs.keys())  # Already sorted newest first

    # If no stage selected, show picker
    if not stage or stage not in STAGE_FILES:
        return render_template(
            "diff.html",
            ticket_id=ticket_id,
            runs=run_timestamps,
            diff=None,
            a="",
            b="",
            mode="workspace",
            stages=list(STAGE_FILES.keys()),
            selected_stage=stage,
        )

    filename = STAGE_FILES[stage]
    workspace_path = WORK_DIR / ticket_id / filename

    # Find latest run with this stage artifact
    last_run_path = None
    last_run_ts = None
    for ts in run_timestamps:
        candidate = RUNS_DIR / ticket_id / ts / stage / filename
        if candidate.exists():
            last_run_path = candidate
            last_run_ts = ts
            break

    if not workspace_path.exists():
        diff_text = f"Workspace file not found: {workspace_path}"
    elif not last_run_path:
        diff_text = f"No previous run artifact found for stage '{stage}'"
    else:
        ta = _read_text(last_run_path).splitlines(keepends=True)
        tb = _read_text(workspace_path).splitlines(keepends=True)
        diff_result = difflib.unified_diff(
            ta, tb,
            fromfile=f"runs/{ticket_id}/{last_run_ts}/{stage}/{filename}",
            tofile=f"work/{ticket_id}/{filename}"
        )
        diff_text = "".join(diff_result) or "(no differences)"

    return render_template(
        "diff.html",
        ticket_id=ticket_id,
        runs=run_timestamps,
        diff=diff_text,
        a=last_run_ts or "",
        b="workspace",
        mode="workspace",
        stages=list(STAGE_FILES.keys()),
        selected_stage=stage,
    )


# ---------------------------------------------------------------------------
# Run Diff (unified diff of run_report.md between two runs)
# ---------------------------------------------------------------------------
@app.get("/ticket/<ticket_id>/diff")
def diff_runs(ticket_id: str):
    if not _safe(ticket_id):
        abort(400)

    a = (request.args.get("a") or "").strip()
    b = (request.args.get("b") or "").strip()

    runs = _list_runs(ticket_id)
    run_timestamps = list(runs.keys())

    # If a and b not provided, show picker
    if not a or not b:
        return render_template("diff.html", ticket_id=ticket_id, runs=run_timestamps, diff=None, a=a, b=b, mode="runs")

    if not (_safe(a) and _safe(b)):
        abort(400)

    pa = RUNS_DIR / ticket_id / a / "run_report.md"
    pb = RUNS_DIR / ticket_id / b / "run_report.md"
    if not (pa.exists() and pb.exists()):
        return render_template("diff.html", ticket_id=ticket_id, runs=run_timestamps, diff="One or both run_report.md files not found.", a=a, b=b, mode="runs")

    ta = _read_text(pa).splitlines(keepends=True)
    tb = _read_text(pb).splitlines(keepends=True)

    diff_result = difflib.unified_diff(ta, tb, fromfile=f"{ticket_id}/{a}", tofile=f"{ticket_id}/{b}")
    diff_text = "".join(diff_result) or "(no differences)"
    return render_template("diff.html", ticket_id=ticket_id, runs=run_timestamps, diff=diff_text, a=a, b=b, mode="runs")


# ---------------------------------------------------------------------------
# API: List projects (for create ticket form)
# ---------------------------------------------------------------------------
@app.get("/api/projects")
def api_projects():
    return jsonify({"projects": _list_projects()})


# ---------------------------------------------------------------------------
# Worker: helpers
# ---------------------------------------------------------------------------

def _read_worker_state() -> Dict[str, Any]:
    """Return the contents of runs/worker.state.json, or a default dict."""
    try:
        return json.loads(WORKER_STATE.read_text(encoding="utf-8"))
    except Exception:
        return {"running": False}


def _worker_is_alive(pid: Optional[int]) -> bool:
    """Return True if *pid* corresponds to a live process."""
    if not pid:
        return False
    try:
        os.kill(int(pid), 0)
        return True
    except (ProcessLookupError, PermissionError, OSError):
        return False


# ---------------------------------------------------------------------------
# Worker: API status endpoint
# ---------------------------------------------------------------------------

@app.get("/api/worker/status")
def api_worker_status():
    state = _read_worker_state()
    running = state.get("running", False)
    pid = state.get("pid")
    # Reconcile state file with OS reality
    if running and not _worker_is_alive(pid):
        running = False
    return jsonify({"ok": True, "worker": {**state, "running": running}})


# ---------------------------------------------------------------------------
# Worker: start / stop
# ---------------------------------------------------------------------------

@app.post("/worker/start")
def worker_start():
    state = _read_worker_state()
    if state.get("running") and _worker_is_alive(state.get("pid")):
        # Already running — nothing to do
        return redirect(url_for("index"))

    env = os.environ.copy()
    env["PYTHONPATH"] = str(REPO_ROOT / "omniforge" / "runner")

    subprocess.Popen(
        [_repo_python(), str(REPO_ROOT / "omniforge" / "viewer" / "worker.py")],
        cwd=str(REPO_ROOT),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
    )

    return redirect(url_for("index"))


@app.post("/worker/stop")
def worker_stop():
    state = _read_worker_state()
    state["running"] = False
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    WORKER_STATE.write_text(json.dumps(state, indent=2), encoding="utf-8")
    return redirect(url_for("index"))


# ---------------------------------------------------------------------------
# Worker: log viewer
# ---------------------------------------------------------------------------

@app.get("/worker/log")
def worker_log_view():
    if not WORKER_LOG.exists():
        return "<pre>No worker log yet.</pre>"
    content = _read_text(WORKER_LOG)
    tail = int(request.args.get("tail", "400"))
    lines = content.splitlines()
    content = "\n".join(lines[-tail:]) if tail > 0 else content
    return f"<pre style='white-space:pre-wrap'>{html_escape(content)}</pre>"


if __name__ == "__main__":
    # Run: python omniforge/viewer/app.py
    app.run(host="127.0.0.1", port=5055, debug=True)
