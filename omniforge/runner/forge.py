#!/usr/bin/env python3
"""OmniForge Labs — Local Agent Runner.

Usage examples::

    python forge.py run --project omnidigest --ticket T-001
    python forge.py run --project omnidigest --ticket T-001 --auto
    python forge.py status --ticket T-001
    python forge.py list
"""

from __future__ import annotations

import argparse
import datetime
import os
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

# ---------------------------------------------------------------------------
# SDLC stage order
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


# ---------------------------------------------------------------------------
# Command execution
# ---------------------------------------------------------------------------


def run_command(cmd: str, cwd: str, log_path: str) -> int:
    """Run *cmd* in a shell, writing combined stdout+stderr to *log_path*.

    Returns the exit code.
    """
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
        )
        log.write(f"\n[exit {result.returncode}]\n")
    return result.returncode


# ---------------------------------------------------------------------------
# Core run logic
# ---------------------------------------------------------------------------


def run_project(
    project: str,
    ticket: str,
    auto: bool = False,
    force_stage: Optional[str] = None,
    board=None,
) -> bool:
    """Execute a ticket through the SDLC stages.

    Parameters
    ----------
    project:
        Project name (must match a directory under ``omniforge/projects/``).
    ticket:
        Ticket identifier (e.g. ``"T-001"``).
    auto:
        When *True*, auto-advance through client gates without prompting.
    force_stage:
        If set, skip all stages before this one (used after a rollback override).
    board:
        An optional pre-constructed board adapter.  Defaults to
        :class:`~adapters.local_board.LocalBoard`.

    Returns
    -------
    bool
        ``True`` if the ticket reached ``delivered``, ``False`` otherwise.
    """
    # Import here to allow tests to inject a mock board.
    if board is None:
        from adapters.local_board import LocalBoard  # noqa: PLC0415

        board = LocalBoard()

    manifest = load_manifest(project)
    gates = load_gates(project)

    timestamp = datetime.datetime.now().strftime("%Y%m%dT%H%M%S")
    run_dir = os.path.join(_RUNS_DIR, ticket, timestamp)
    os.makedirs(run_dir, exist_ok=True)

    board.upsert_ticket(
        ticket,
        {
            "project": project,
            "status": "running",
            "run_dir": run_dir,
            "started_at": timestamp,
        },
    )

    stage_commands: Dict[str, Any] = manifest.get("stages", {}) or {}
    pause_at: List[str] = gates.get("pause_at", []) or []
    rollback_map: Dict[str, str] = gates.get("rollback", {}) or {}
    escalation_threshold: int = gates.get("escalation_threshold", 2)

    # Determine starting index when resuming from a force_stage.
    start_index = 0
    if force_stage:
        if force_stage not in SDLC_STAGES:
            print(f"✗ Unknown stage '{force_stage}'. Valid stages: {SDLC_STAGES}")
            return False
        start_index = SDLC_STAGES.index(force_stage)

    for stage in SDLC_STAGES[start_index:]:
        cmds = stage_commands.get(stage)
        if not cmds:
            # No commands defined for this stage — auto-pass.
            continue

        # Normalise to list.
        if isinstance(cmds, str):
            cmds = [cmds]

        # Client gate: pause for approval unless --auto.
        if stage in pause_at and not auto:
            print(f"\n⛔  Gate: {stage} — awaiting client approval")
            print(f"   (pass --auto to skip interactive gates)")
            try:
                answer = input("   Continue? [y/N] ").strip().lower()
            except EOFError:
                answer = "n"
            if answer != "y":
                board.upsert_ticket(ticket, {"status": f"paused_at_{stage}"})
                print(f"\nPaused at '{stage}'.  Re-run with the same command to resume.")
                return False

        print(f"\n▶  Stage: {stage}")
        stage_log = os.path.join(run_dir, f"{stage}.log")
        failed = False

        for cmd in cmds:
            print(f"   $ {cmd}")
            rc = run_command(cmd, os.getcwd(), stage_log)
            if rc != 0:
                rollback_to = rollback_map.get(stage, "implement")
                print(f"   ✗ Failed (exit {rc}) — log: {stage_log}")
                print(f"   ↩  Rolling back to: {rollback_to}")

                # Track rollback count for escalation.
                existing = board.get_ticket(ticket) or {}
                rollback_counts: Dict[str, int] = dict(
                    existing.get("rollback_counts", {})
                )
                rollback_counts[stage] = rollback_counts.get(stage, 0) + 1

                # Escalate if threshold exceeded.
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
                failed = True
                break

        if failed:
            return False

        print(f"   ✓ {stage} passed")
        board.upsert_ticket(ticket, {"last_passed_stage": stage})

    board.upsert_ticket(ticket, {"status": "delivered", "delivered_at": timestamp})
    print(f"\n✅  Ticket {ticket} delivered.  Artifacts in: {run_dir}")
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
        help="Auto-advance through client gates without interactive prompts",
    )
    run_p.add_argument(
        "--force-stage",
        dest="force_stage",
        metavar="STAGE",
        help="Skip all stages before STAGE (resume from a rollback point)",
    )
    run_p.set_defaults(func=cmd_run)

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
