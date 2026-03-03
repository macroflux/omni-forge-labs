#!/usr/bin/env python3
"""OmniForge Labs — Local Agent Runner.

Usage examples::

    python forge.py run --project omnidigest --ticket T-001
    python forge.py run --project omnidigest --ticket T-001 --auto
    python forge.py approve --ticket T-001 --stage design
    python forge.py approve --ticket T-001 --stage design --by "Chris"
    python forge.py status --ticket T-001
    python forge.py list
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import shutil
import subprocess
import sys
from typing import Any, Dict, List, Optional

import yaml

# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

_RUNNER_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.abspath(os.path.join(_RUNNER_DIR, ".."))
_PROJECTS_DIR = os.path.join(_REPO_ROOT, "projects")
# runs/ sits at the repository root (one level above omniforge/), with a
# fallback guard in case the directory resolves to the filesystem root.
_RUNS_DIR = os.path.join(os.path.dirname(_REPO_ROOT), "runs")
if not os.path.isabs(_RUNS_DIR) or _RUNS_DIR == "/runs":
    _RUNS_DIR = os.path.join(_REPO_ROOT, "..", "runs")
_RUNS_DIR = os.path.normpath(_RUNS_DIR)

# Workspace directory for editable ticket docs (before run snapshot)
_WORK_DIR = os.path.join(_RUNS_DIR, "work")

# ---------------------------------------------------------------------------
# SDLC stage order and required artifact names
# ---------------------------------------------------------------------------

SDLC_STAGES: List[str] = [
    "intake",
    "plan",
    "design",
    "research",
    "implement",
    "test",
    "integrate",
    "deliver",
]

# After a stage's commands succeed, this file must exist in the per-stage directory
# (runs/<ticket>/<timestamp>/<stage>/).
STAGE_ARTIFACTS: Dict[str, str] = {
    "intake": "intake.md",
    "plan": "plan.md",
    "design": "design.md",
    "research": "research.md",
    "implement": "implementation.md",
    "test": "test_report.md",
    "integrate": "integration_report.md",
    "deliver": "delivery.md",
}

# ---------------------------------------------------------------------------
# Manifest / gate helpers
# ---------------------------------------------------------------------------


def load_manifest(project: str) -> Dict[str, Any]:
    """Load and return the project manifest YAML."""
    path = os.path.join(_PROJECTS_DIR, project, "manifest.yaml")
    if not os.path.exists(path):
        raise FileNotFoundError(f"Manifest not found: {path}")
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def load_gates(project: str) -> Dict[str, Any]:
    """Load and return the project gates YAML."""
    path = os.path.join(_PROJECTS_DIR, project, "gates.yaml")
    if not os.path.exists(path):
        raise FileNotFoundError(f"Gates config not found: {path}")
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def copy_workspace_to_run(ticket: str, run_dir: str) -> None:
    """Copy workspace docs (intake, plan, design, research) into run stage folders.

    This snapshots editable workspace files into the immutable run evidence.
    For early stages (intake/plan/design/research), the workspace file becomes
    the required artifact if no command generates one.
    """
    work_dir = os.path.join(_WORK_DIR, ticket)
    if not os.path.isdir(work_dir):
        return

    # Map workspace files to their stage artifact names
    workspace_to_artifact = {
        "intake.md": ("intake", "intake.md"),
        "plan.md": ("plan", "plan.md"),
        "design.md": ("design", "design.md"),
        "research.md": ("research", "research.md"),
    }

    for ws_file, (stage, artifact_name) in workspace_to_artifact.items():
        src = os.path.join(work_dir, ws_file)
        if os.path.isfile(src):
            stage_dir = os.path.join(run_dir, stage)
            os.makedirs(stage_dir, exist_ok=True)
            dst = os.path.join(stage_dir, artifact_name)
            # Only copy if artifact doesn't already exist (don't overwrite command output)
            if not os.path.exists(dst):
                try:
                    shutil.copy2(src, dst)
                except Exception as e:
                    print(f"⚠  Workspace snapshot failed for {ticket} {ws_file}: {e}")


# ---------------------------------------------------------------------------
# Command execution
# ---------------------------------------------------------------------------


def run_command(
    cmd: str,
    cwd: str,
    log_path: str,
    extra_env: Optional[Dict[str, str]] = None,
) -> int:
    """Run *cmd* in a shell, writing combined stdout+stderr to *log_path*.

    Parameters
    ----------
    cmd:
        Shell command string.
    cwd:
        Working directory for the subprocess.
    log_path:
        Append stdout + stderr here.
    extra_env:
        Additional environment variables merged on top of ``os.environ``.
        Used to inject ``FORGE_RUN_DIR``, ``FORGE_STAGE_DIR``, ``FORGE_TICKET``, etc.

    Returns
    -------
    int
        Exit code of the command.
    """
    env = os.environ.copy()
    if extra_env:
        env.update(extra_env)
    with open(log_path, "a", encoding="utf-8") as log:
        log.write(f"$ {cmd}\n")
        log.flush()
        result = subprocess.run(
            cmd,
            shell=True,
            cwd=cwd,
            stdout=log,
            stderr=subprocess.STDOUT,
            text=True,
            env=env,
        )
        log.write(f"\n[exit {result.returncode}]\n")
    return result.returncode


# ---------------------------------------------------------------------------
# Assertion runners
# ---------------------------------------------------------------------------


def run_asserts(
    asserts: List[Dict[str, Any]],
    resolved_cwd: str,
) -> Optional[str]:
    """Run a list of assertions against the filesystem.

    Returns the first failure message, or *None* if all pass.

    Supported types
    ---------------
    ``file_exists``
        Checks that ``path`` exists (relative to *resolved_cwd*, or absolute).
    ``json_has_keys``
        Checks that ``path`` is valid JSON and contains every key in ``keys``.
    ``json_array_min_length``
        Checks that the value reached by a dot-path ``key`` inside ``path`` is
        a list with at least ``min`` items (default: 1).
        Dot-path example: ``"categories.Technology"``.
    """
    for assertion in asserts:
        atype = assertion.get("type")
        raw_path = assertion.get("path", "")
        if os.path.isabs(raw_path):
            full_path = raw_path
        else:
            full_path = os.path.normpath(os.path.join(resolved_cwd, raw_path))

        if atype == "file_exists":
            if not os.path.exists(full_path):
                return f"file_exists failed: {full_path} not found"

        elif atype == "json_has_keys":
            if not os.path.exists(full_path):
                return f"json_has_keys failed: {full_path} not found"
            try:
                with open(full_path, encoding="utf-8") as fh:
                    data = json.load(fh)
            except (json.JSONDecodeError, OSError) as exc:
                return f"json_has_keys failed: cannot read {full_path}: {exc}"
            missing = [k for k in assertion.get("keys", []) if k not in data]
            if missing:
                return f"json_has_keys failed: {full_path} missing keys: {missing}"

        elif atype == "json_array_min_length":
            if not os.path.exists(full_path):
                return f"json_array_min_length failed: {full_path} not found"
            try:
                with open(full_path, encoding="utf-8") as fh:
                    data = json.load(fh)
            except (json.JSONDecodeError, OSError) as exc:
                return f"json_array_min_length failed: cannot read {full_path}: {exc}"
            key_path = assertion.get("key", "")
            min_len = assertion.get("min", 1)
            # Traverse dot-path keys (e.g. "categories.Technology").
            # node starts as the parsed JSON object and narrows at each step.
            node: Dict[str, Any] = data
            for part in key_path.split("."):
                if not isinstance(node, dict) or part not in node:
                    return (
                        f"json_array_min_length failed: key path '{key_path}' "
                        f"not found in {full_path}"
                    )
                node = node[part]
            if not isinstance(node, list):
                return (
                    f"json_array_min_length failed: '{key_path}' is not a list "
                    f"in {full_path}"
                )
            if len(node) < min_len:
                return (
                    f"json_array_min_length failed: '{key_path}' has {len(node)} "
                    f"items, need >= {min_len} in {full_path}"
                )

        else:
            return f"Unknown assertion type: {atype!r}"

    return None


# ---------------------------------------------------------------------------
# Run report
# ---------------------------------------------------------------------------


def write_run_report(
    run_dir: str,
    ticket: str,
    project: str,
    timestamp: str,
    stages_run: List[str],
    stage_results: Dict[str, str],
    pause_stage: Optional[str] = None,
    rollback_to: Optional[str] = None,
    resume_cmd: Optional[str] = None,
) -> None:
    """Write a Markdown summary to *run_dir*/run_report.md."""
    lines = [
        "# OmniForge Run Report",
        "",
        f"**Ticket:** {ticket}",
        f"**Project:** {project}",
        f"**Timestamp:** {timestamp}",
        "",
        "## Stage Results",
        "",
        "| Stage | Result |",
        "|-------|--------|",
    ]
    for stage in stages_run:
        result = stage_results.get(stage, "skipped")
        lines.append(f"| {stage} | {result} |")
    lines.append("")

    if pause_stage:
        lines += [
            f"## Paused at: {pause_stage}",
            "",
            f"Awaiting approval for stage `{pause_stage}` before continuing.",
            "",
            "**Next steps:**",
            "```bash",
            f"python forge.py approve --ticket {ticket} --stage {pause_stage}",
            f"python forge.py run --project {project} --ticket {ticket}",
            "```",
            "",
        ]
    elif rollback_to:
        lines += [
            f"## Failed — Rollback to: {rollback_to}",
            "",
            "Fix the issue then resume:",
            "```bash",
        ]
        if resume_cmd:
            lines.append(resume_cmd)
        lines += ["```", ""]
    else:
        lines += ["## Status: Delivered ✅", ""]

    report_path = os.path.join(run_dir, "run_report.md")
    with open(report_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")


# ---------------------------------------------------------------------------
# Board history helper
# ---------------------------------------------------------------------------


def _append_history(board: Any, ticket: str, event: Dict[str, Any]) -> None:
    """Append *event* to the ticket's ``history`` list on the board."""
    existing = board.get_ticket(ticket) or {}
    history = list(existing.get("history") or [])
    history.append(event)
    board.upsert_ticket(ticket, {"history": history})


# ---------------------------------------------------------------------------
# Core run logic
# ---------------------------------------------------------------------------


def run_project(
    project: str,
    ticket: str,
    auto: bool = False,
    force_stage: Optional[str] = None,
    board: Any = None,
) -> bool:
    """Execute a ticket through the SDLC stages.

    Parameters
    ----------
    project:
        Project name (must match a directory under ``omniforge/projects/``).
    ticket:
        Ticket identifier (e.g. ``"T-001"``).
    auto:
        When *True*, skip gate approval checks and advance automatically.
    force_stage:
        If set, skip all stages before this one (resume from a rollback point).
    board:
        Optional pre-constructed board adapter.  Defaults to
        :class:`~adapters.local_board.LocalBoard`.

    Returns
    -------
    bool
        ``True`` if the ticket reached ``delivered``, ``False`` otherwise.
        A ``False`` return on a gate pause is a clean exit (not an error).
    """
    if board is None:
        from adapters.local_board import LocalBoard  # noqa: PLC0415

        board = LocalBoard()

    manifest = load_manifest(project)
    gates = load_gates(project)

    timestamp = datetime.datetime.now().strftime("%Y%m%dT%H%M%S")
    run_dir = os.path.join(_RUNS_DIR, ticket, timestamp)
    os.makedirs(run_dir, exist_ok=True)

    # Copy workspace docs (intake, plan, design, research) into run as starting artifacts
    copy_workspace_to_run(ticket, run_dir)

    # Resolve working directory for commands.
    # manifest.repo_root is a path relative to _RUNNER_DIR (or absolute).
    repo_root_raw = manifest.get("repo_root")
    if repo_root_raw:
        if os.path.isabs(repo_root_raw):
            resolved_cwd = repo_root_raw
        else:
            resolved_cwd = os.path.normpath(os.path.join(_RUNNER_DIR, repo_root_raw))
    else:
        resolved_cwd = _REPO_ROOT

    # Preserve approvals / history across runs (for resume after pause/rollback).
    existing_ticket = board.get_ticket(ticket) or {}
    board.upsert_ticket(
        ticket,
        {
            "project": project,
            "status": "running",
            "stage": None,
            "run_dir": run_dir,
            "started_at": timestamp,
            "approvals": existing_ticket.get("approvals") or {},
            "approvals_meta": existing_ticket.get("approvals_meta") or {},
            "rollback_counts": existing_ticket.get("rollback_counts") or {},
            "history": existing_ticket.get("history") or [],
        },
    )
    _append_history(
        board,
        ticket,
        {"event": "run_started", "timestamp": timestamp, "project": project},
    )

    stage_commands: Dict[str, Any] = manifest.get("stages") or {}
    stage_asserts: Dict[str, Any] = manifest.get("asserts") or {}
    pause_at: List[str] = gates.get("pause_at") or []
    rollback_map: Dict[str, str] = gates.get("rollback") or {}
    escalation_threshold: int = gates.get("escalation_threshold", 2)

    # Determine starting index when resuming via --force-stage.
    start_index = 0
    if force_stage:
        if force_stage not in SDLC_STAGES:
            print(f"✗ Unknown stage '{force_stage}'. Valid stages: {SDLC_STAGES}")
            return False
        start_index = SDLC_STAGES.index(force_stage)

    # Environment variables injected into every command subprocess.
    env_extras: Dict[str, str] = {
        "FORGE_RUN_DIR": run_dir,
        "FORGE_TICKET": ticket,
        "FORGE_PROJECT": project,
    }

    stages_run: List[str] = []
    stage_results: Dict[str, str] = {}

    for stage in SDLC_STAGES[start_index:]:
        if stage not in stage_commands:
            # Stage not part of this project — skip entirely.
            continue

        # `or []` handles a YAML null (None) value — stage key present but no commands.
        cmds_raw = stage_commands.get(stage) or []
        # Normalise to list.
        if isinstance(cmds_raw, str):
            cmds_raw = [cmds_raw]

        # Each entry is a plain string or a dict {cmd, cwd}.
        cmds: List[Dict[str, str]] = []
        for c in cmds_raw:
            if isinstance(c, dict):
                cmd_cwd_raw = c.get("cwd", "")
                if cmd_cwd_raw:
                    if os.path.isabs(cmd_cwd_raw):
                        effective_cwd = cmd_cwd_raw
                    else:
                        effective_cwd = os.path.normpath(
                            os.path.join(resolved_cwd, cmd_cwd_raw)
                        )
                else:
                    effective_cwd = resolved_cwd
                cmds.append({"cmd": c["cmd"], "cwd": effective_cwd})
            else:
                cmds.append({"cmd": c, "cwd": resolved_cwd})

        # Update board with current stage.
        board.upsert_ticket(ticket, {"stage": stage})

        # Create per-stage directory for logs and artifacts.
        stage_dir = os.path.join(run_dir, stage)
        os.makedirs(stage_dir, exist_ok=True)
        stage_log = os.path.join(stage_dir, "stage.log")
        env_extras["FORGE_STAGE_DIR"] = stage_dir

        # ── Gate check ────────────────────────────────────────────────────
        if stage in pause_at and not auto:
            existing_now = board.get_ticket(ticket) or {}
            approvals = existing_now.get("approvals") or {}
            if not approvals.get(stage):
                board.upsert_ticket(ticket, {"status": f"paused_at_{stage}"})
                _append_history(
                    board,
                    ticket,
                    {
                        "event": "paused",
                        "stage": stage,
                        "timestamp": datetime.datetime.now(
                            datetime.timezone.utc
                        ).isoformat(),
                    },
                )
                print(f"\n⛔  Gate: {stage} — awaiting approval")
                print(
                    f"   To approve:  python forge.py approve "
                    f"--ticket {ticket} --stage {stage}"
                )
                print(
                    f"   To resume:   python forge.py run "
                    f"--project {project} --ticket {ticket}"
                )
                write_run_report(
                    run_dir,
                    ticket,
                    project,
                    timestamp,
                    stages_run,
                    stage_results,
                    pause_stage=stage,
                )
                return False

        stages_run.append(stage)
        print(f"\n▶  Stage: {stage}")
        failed = False
        fail_reason = ""

        # ── Execute commands ───────────────────────────────────────────────
        for cmd_entry in cmds:
            print(f"   $ {cmd_entry['cmd']}")
            rc = run_command(
                cmd_entry["cmd"],
                cmd_entry["cwd"],
                stage_log,
                extra_env=env_extras,
            )
            if rc != 0:
                fail_reason = f"command failed (exit {rc}): {cmd_entry['cmd']}"
                failed = True
                break

        # ── Artifact enforcement ───────────────────────────────────────────
        if not failed:
            artifact_name = STAGE_ARTIFACTS.get(stage)
            if artifact_name:
                artifact_path = os.path.join(stage_dir, artifact_name)
                if not os.path.exists(artifact_path):
                    fail_reason = (
                        f"missing required artifact: {artifact_name} "
                        f"(expected at {artifact_path}). "
                        f"Stage commands must write this file to "
                        f"$FORGE_STAGE_DIR/{artifact_name}"
                    )
                    failed = True

        # ── Assertions ─────────────────────────────────────────────────────
        if not failed:
            assert_list = stage_asserts.get(stage) or []
            if assert_list:
                err = run_asserts(assert_list, resolved_cwd)
                if err:
                    fail_reason = f"assertion failed: {err}"
                    failed = True

        # ── Handle failure ─────────────────────────────────────────────────
        if failed:
            rollback_to = rollback_map.get(stage, "implement")
            print(f"   ✗ {stage} failed — {fail_reason}")
            print(f"   ↩  Rolling back to: {rollback_to}")

            existing_now = board.get_ticket(ticket) or {}
            rollback_counts: Dict[str, int] = dict(
                existing_now.get("rollback_counts") or {}
            )
            rollback_counts[stage] = rollback_counts.get(stage, 0) + 1

            effective_rollback = rollback_to
            if rollback_counts[stage] >= escalation_threshold:
                idx = SDLC_STAGES.index(rollback_to)
                if idx > 0:
                    effective_rollback = SDLC_STAGES[idx - 1]
                    print(
                        f"   ⚠  Escalating to: {effective_rollback} "
                        f"(rollback threshold {escalation_threshold} reached)"
                    )

            board.upsert_ticket(
                ticket,
                {
                    "status": f"failed_at_{stage}",
                    "rollback_to": effective_rollback,
                    "rollback_counts": rollback_counts,
                    "last_log": stage_log,
                },
            )
            stage_results[stage] = f"FAIL — {fail_reason}"
            _append_history(
                board,
                ticket,
                {
                    "event": "stage_failed",
                    "stage": stage,
                    "reason": fail_reason,
                    "rollback_to": effective_rollback,
                    "timestamp": datetime.datetime.now(
                        datetime.timezone.utc
                    ).isoformat(),
                },
            )
            resume_cmd = (
                f"python forge.py run --project {project} "
                f"--ticket {ticket} --force-stage {effective_rollback}"
            )
            write_run_report(
                run_dir,
                ticket,
                project,
                timestamp,
                stages_run,
                stage_results,
                rollback_to=effective_rollback,
                resume_cmd=resume_cmd,
            )
            return False

        # ── Stage passed ───────────────────────────────────────────────────
        stage_results[stage] = "PASS"
        print(f"   ✓ {stage} passed")
        board.upsert_ticket(ticket, {"last_passed_stage": stage, "last_log": stage_log})
        _append_history(
            board,
            ticket,
            {
                "event": "stage_passed",
                "stage": stage,
                "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            },
        )

    board.upsert_ticket(ticket, {"status": "delivered", "delivered_at": timestamp})
    _append_history(board, ticket, {"event": "delivered", "timestamp": timestamp})
    write_run_report(run_dir, ticket, project, timestamp, stages_run, stage_results)
    print(f"\n✅  Ticket {ticket} delivered.  Run report: {run_dir}/run_report.md")
    return True


# ---------------------------------------------------------------------------
# CLI commands
# ---------------------------------------------------------------------------


def cmd_run(args: argparse.Namespace) -> None:
    """Handle the ``forge run`` sub-command."""
    sys.path.insert(0, _RUNNER_DIR)
    run_project(
        project=args.project,
        ticket=args.ticket,
        auto=args.auto,
        force_stage=getattr(args, "force_stage", None),
    )


def cmd_approve(args: argparse.Namespace) -> None:
    """Handle the ``forge approve`` sub-command."""
    sys.path.insert(0, _RUNNER_DIR)
    from adapters.local_board import LocalBoard  # noqa: PLC0415

    board = LocalBoard()
    approver = getattr(args, "by", None) or "unknown"
    ticket = board.approve_stage(args.ticket, args.stage, by=approver)
    print(
        f"✅  Stage '{args.stage}' approved for ticket {args.ticket}  (by: {approver})"
    )
    project = ticket.get("project") or "<your_project>"
    print(
        f"   To resume:  python forge.py run --project {project} "
        f"--ticket {args.ticket}"
    )


def cmd_status(args: argparse.Namespace) -> None:
    """Handle the ``forge status`` sub-command."""
    sys.path.insert(0, _RUNNER_DIR)
    from adapters.local_board import LocalBoard  # noqa: PLC0415

    board = LocalBoard()
    ticket = board.get_ticket(args.ticket)
    if ticket:
        print(yaml.dump(ticket, default_flow_style=False, sort_keys=True))
    else:
        print(f"Ticket '{args.ticket}' not found on the local board.")


def cmd_list(args: argparse.Namespace) -> None:  # noqa: ARG001
    """Handle the ``forge list`` sub-command."""
    sys.path.insert(0, _RUNNER_DIR)
    from adapters.local_board import LocalBoard  # noqa: PLC0415

    board = LocalBoard()
    tickets = board.list_tickets()
    if not tickets:
        print("No tickets found on the local board.")
        return
    for tid, data in sorted(tickets.items()):
        status = data.get("status", "unknown")
        project = data.get("project", "?")
        print(f"  {tid}  [{project}]  {status}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    """Return the top-level argument parser."""
    parser = argparse.ArgumentParser(
        prog="forge",
        description="OmniForge Labs — Local Agent Runner",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # forge run
    run_p = sub.add_parser("run", help="Run a project ticket through the SDLC")
    run_p.add_argument("--project", required=True, help="Project name (e.g. omnidigest)")
    run_p.add_argument("--ticket", required=True, help="Ticket ID (e.g. T-001)")
    run_p.add_argument(
        "--auto",
        action="store_true",
        help="Auto-advance through client gates without checking approvals",
    )
    run_p.add_argument(
        "--force-stage",
        dest="force_stage",
        metavar="STAGE",
        help="Skip all stages before STAGE (resume from a rollback point)",
    )
    run_p.set_defaults(func=cmd_run)

    # forge approve
    approve_p = sub.add_parser("approve", help="Approve a gate stage for a ticket")
    approve_p.add_argument("--ticket", required=True, help="Ticket ID (e.g. T-001)")
    approve_p.add_argument(
        "--stage", required=True, help="Stage to approve (e.g. design)"
    )
    approve_p.add_argument("--by", default=None, help="Approver name (optional)")
    approve_p.set_defaults(func=cmd_approve)

    # forge status
    status_p = sub.add_parser("status", help="Show ticket status")
    status_p.add_argument("--ticket", required=True, help="Ticket ID")
    status_p.set_defaults(func=cmd_status)

    # forge list
    list_p = sub.add_parser("list", help="List all tickets on the local board")
    list_p.set_defaults(func=cmd_list)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
