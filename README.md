# OmniForge Labs — Architecture & Operations Reference

> **One document that explains everything:** architecture, goals, repo layout, operational
> flow, CLI reference, viewer UI, worker loop, and how to ground an LLM against this repo.

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Architecture Goals](#2-architecture-goals)
3. [Quick Start](#3-quick-start)
4. [Full Repository Layout](#4-full-repository-layout)
5. [Core Domain Model](#5-core-domain-model)
6. [SDLC Stage Pipeline](#6-sdlc-stage-pipeline)
7. [Forge CLI Reference](#7-forge-cli-reference)
8. [Viewer UI (Dashboard)](#8-viewer-ui-dashboard)
9. [Unattended Worker Loop](#9-unattended-worker-loop)
10. [Project Configuration Reference](#10-project-configuration-reference)
11. [Board & State Files](#11-board--state-files)
12. [Running Tests](#12-running-tests)
13. [Using with LLMs / OpenAI](#13-using-with-llms--openai)
14. [Glossary](#14-glossary)

---

## 1) Executive Summary

**OmniForge Labs** is a governance-driven SDLC orchestration framework that executes
project work as *tickets* through an eight-stage pipeline, enforcing quality gates,
capturing evidence artifacts, and recording rollback history — all with a pluggable
board backend (local JSON by default, GitHub Projects as an optional adapter).

The system has three runtime layers:

| Layer | Component | Role |
|-------|-----------|------|
| Execution engine | `omniforge/runner/forge.py` | Runs SDLC stages, enforces gates & artifacts |
| Web dashboard | `omniforge/viewer/app.py` | Flask UI to create tickets, run them, approve gates, inspect artifacts |
| Unattended worker | `omniforge/viewer/worker.py` | Background loop that auto-processes the backlog one ticket at a time |

Six named roles (Rowan, Kade, Nyx, Vega, Quinn, Ember) provide an LLM-facing operating
model: each role document defines responsibilities, decision rights, and expected outputs so
that an AI assistant can be grounded to behave like a specific team member.

---

## 2) Architecture Goals

- **Repeatable delivery** — every ticket follows the same eight-stage SDLC; no ad-hoc shortcuts.
- **Evidence-first** — each stage must produce a required artifact (Markdown file) before the
  runner advances. Missing artifacts cause the stage to fail and trigger rollback.
- **Human-in-the-loop gates** — three stages (`design`, `test`, `deliver`) pause for explicit
  approval before proceeding, preventing fully automated delivery without human sign-off.
- **LLM-compatible operating model** — role charters + playbooks are written as grounding
  documents so an AI assistant can be assigned a role and reason about what to do next.
- **Pluggable backends** — the board adapter interface separates core orchestration logic from
  the state-storage mechanism; swapping in GitHub Projects does not require touching `forge.py`.
- **Local-first, no cloud required** — everything runs on localhost with standard Python + Flask.

---

## 3) Quick Start

### Install dependencies

```bash
pip install -r requirements.txt
```

### Run the forge CLI (terminal / headless)

```bash
# Run the OmniDigest project through all SDLC stages, auto-approving gates
PYTHONPATH=omniforge/runner python omniforge/runner/forge.py run \
  --project omnidigest --ticket T-001 --auto

# Approve a gate stage manually (e.g. after reviewing design docs)
PYTHONPATH=omniforge/runner python omniforge/runner/forge.py approve \
  --ticket T-001 --stage design --by "Chris"

# Resume after a gate approval (or from a rollback point)
PYTHONPATH=omniforge/runner python omniforge/runner/forge.py run \
  --project omnidigest --ticket T-001

# Check a ticket's current status
PYTHONPATH=omniforge/runner python omniforge/runner/forge.py status --ticket T-001

# List all tickets on the board
PYTHONPATH=omniforge/runner python omniforge/runner/forge.py list
```

### Start the web viewer (dashboard)

```bash
PYTHONPATH=. python omniforge/viewer/app.py
# Open http://127.0.0.1:5055 in your browser
```

The viewer provides a full dashboard UI for creating tickets, triggering runs, approving
gates, editing workspace documents, inspecting run artifacts, and starting/stopping the
unattended worker loop — all without touching the CLI.

---

## 4) Full Repository Layout

```
omni-forge-labs/                     ← repository root
├── README.md                        ← this document
├── requirements.txt                 ← Python dependencies (pyyaml, pytest, flask)
├── conftest.py                      ← pytest path setup (adds repo root + runner to sys.path)
├── folder_structure.txt             ← tree snapshot / reference (informational)
│
├── omniforge/                       ← main Python package
│   ├── __init__.py
│   │
│   ├── charter/                     ← governance: org identity + named roles
│   │   ├── company_charter.md       ← mission, principles, decision framework
│   │   └── roles/
│   │       ├── rowan_pm.md          ← PM / Delivery Lead: scope, gates, momentum
│   │       ├── kade_architect.md    ← Architect: design, standards, NFRs
│   │       ├── nyx_research.md      ← Research: options survey, CVE/version checks
│   │       ├── vega_dev.md          ← Dev Lead: implementation, code quality
│   │       ├── quinn_qa.md          ← QA / Test: test strategy, evidence, acceptance
│   │       └── ember_release.md     ← Release / Ops: packaging, runbook, delivery
│   │
│   ├── playbooks/                   ← process: how work proceeds
│   │   ├── sdlc_stages.md           ← eight-stage pipeline, owners, gate rules
│   │   └── rollback_rules.md        ← rollback triggers, targets, escalation policy
│   │
│   ├── projects/                    ← project definitions (one folder per project)
│   │   └── omnidigest/
│   │       ├── manifest.yaml        ← stage commands, assertions, artifact_folders
│   │       └── gates.yaml           ← pause_at stages, rollback map, escalation_threshold
│   │
│   ├── runner/                      ← execution engine
│   │   ├── __init__.py
│   │   ├── forge.py                 ← CLI orchestrator: run / approve / status / list
│   │   └── adapters/
│   │       ├── __init__.py
│   │       ├── local_board.py       ← JSON ticket board (runs/board.json)
│   │       └── github_projects.py   ← GitHub Projects adapter (stub, future use)
│   │
│   └── viewer/                      ← web dashboard (Flask)
│       ├── __init__.py
│       ├── app.py                   ← Flask app, all HTTP routes
│       ├── worker.py                ← unattended worker loop (spawned by app.py)
│       └── templates/
│           ├── layout.html          ← base template (nav, CSS reset)
│           ├── index.html           ← dashboard: ticket table, create form, worker card
│           ├── ticket.html          ← ticket detail: run, approve, workspace, history
│           ├── run.html             ← run detail: per-stage logs and artifacts
│           ├── diff.html            ← unified diff: workspace vs run, or run vs run
│           └── playbook.html        ← read-only playbook/charter viewer
│
├── tests/
│   ├── test_forge.py                ← unit tests for forge.py logic
│   ├── test_local_board.py          ← unit tests for LocalBoard adapter
│   └── test_worker.py               ← unit tests for worker.py (_is_runnable, _next_ticket, etc.)
│
└── runs/                            ← runtime data (git-ignored)
    ├── board.json                   ← live ticket board (written by LocalBoard)
    ├── worker.log                   ← unattended worker activity log
    ├── worker.state.json            ← worker lifecycle state (running, pid, started_at)
    └── <ticket_id>/
        └── <YYYYMMDDTHHMMSS>/       ← one timestamped folder per run
            ├── run_report.md        ← Markdown summary of this run
            └── <stage>/
                ├── stage.log        ← combined stdout+stderr for stage commands
                └── <artifact>.md    ← required artifact produced by the stage
```

> **`runs/` is git-ignored.** All execution state, logs, and artifacts are local only.

---

## 5) Core Domain Model

### 5.1 Charter (governance layer)

`omniforge/charter/` defines **who we are** and **who does what**.

- `company_charter.md` — the organizational "constitution": mission, principles, and the
  decision framework that governs all choices.
- `roles/<name>.md` — one file per named role. Each document describes that role's
  responsibilities, decision rights, and expected deliverables. When feeding this repo to an
  LLM, a role document becomes the *system prompt* for that agent persona.

### 5.2 Playbooks (process layer)

`omniforge/playbooks/` defines **how work proceeds**.

- `sdlc_stages.md` — defines the eight SDLC stages in order, what "done" means for each,
  and which stages have client gates.
- `rollback_rules.md` — defines rollback trigger conditions, rollback targets per stage, and
  the escalation policy when repeated failures occur at the same stage.

### 5.3 Projects (configuration layer)

`omniforge/projects/<project>/` defines **what we are building**.

- `manifest.yaml` — the project's stage commands, assertion checks, artifact folders, and
  working directory. The runner loads this to know what shell commands to execute at each stage.
- `gates.yaml` — which stages pause for human approval (`pause_at`), where to roll back on
  failure (`rollback`), and how many failures before escalating upstream (`escalation_threshold`).

### 5.4 Runner / Forge (execution layer)

`omniforge/runner/forge.py` is the **central orchestrator**:

1. Loads project `manifest.yaml` and `gates.yaml`.
2. Copies workspace documents (intake, plan, design, research) from `runs/work/<ticket>/`
   into the run folder as initial evidence artifacts.
3. Walks the SDLC stage list in order (or from `--force-stage` if resuming).
4. At each stage: checks gate approval, executes shell commands, enforces the required
   artifact, runs assertions, and handles failure/rollback if anything fails.
5. On success, the ticket reaches `delivered` and a `run_report.md` is written.
6. Reads and writes ticket state through a board adapter (`LocalBoard` by default).

### 5.5 Adapters (integration layer)

`omniforge/runner/adapters/` provides a pluggable interface to different board backends.

- `local_board.py` — stores all ticket state in `runs/board.json` as a flat JSON dictionary.
  No external services required.
- `github_projects.py` — stub adapter for GitHub Projects integration (future use).

### 5.6 Viewer / Worker (interaction layer)

- `omniforge/viewer/app.py` — a Flask web app that wraps all runner operations in a browser
  UI. It spawns `forge.py` as a detached subprocess and reads board state to render dashboards.
- `omniforge/viewer/worker.py` — a standalone background process (also a subprocess spawned
  by the Flask app) that continuously polls the board and processes runnable tickets one at a
  time without human intervention.

---

## 6) SDLC Stage Pipeline

```
intake → plan → design ⛔ → research → implement → test ⛔ → integrate → deliver ⛔
```

Stages marked **⛔** are **client gates** — the runner sets the ticket status to
`paused_at_<stage>` and halts until an explicit approval is recorded on the board.
Pass `--auto` to skip gate checks (useful in CI or fully automated pipelines).

### Stage details

| Stage | Required artifact | Gate? | Default rollback target |
|-------|------------------|-------|------------------------|
| `intake` | `intake.md` | — | — |
| `plan` | `plan.md` | — | `intake` |
| `design` | `design.md` | ⛔ | `plan` |
| `research` | `research.md` | — | `design` |
| `implement` | `implementation.md` | — | `design` |
| `test` | `test_report.md` | ⛔ | `implement` |
| `integrate` | `integration_report.md` | — | `implement` |
| `deliver` | `delivery.md` | ⛔ | `test` |

**Artifact enforcement:** After a stage's commands succeed, the runner checks that the
required artifact file exists at `$FORGE_STAGE_DIR/<artifact>.md`. If it is missing, the
stage fails and triggers rollback just like a failed command.

**Escalation:** After `escalation_threshold` (default 2) consecutive rollbacks to the same
stage, the runner automatically escalates one step further upstream.

**Environment variables injected into every stage command subprocess:**

| Variable | Value |
|----------|-------|
| `FORGE_RUN_DIR` | absolute path to the timestamped run folder |
| `FORGE_STAGE_DIR` | absolute path to the current stage sub-folder |
| `FORGE_TICKET` | ticket ID |
| `FORGE_PROJECT` | project name |

---

## 7) Forge CLI Reference

The CLI entry point is `omniforge/runner/forge.py`. Always set `PYTHONPATH=omniforge/runner`
(or `PYTHONPATH=.` when running from the repo root via the viewer) so `forge.py` can import
the board adapters.

### `forge run` — execute a ticket

```bash
PYTHONPATH=omniforge/runner python omniforge/runner/forge.py run \
  --project <project> \
  --ticket  <ticket_id> \
  [--auto] \
  [--force-stage <stage>]
```

| Flag | Description |
|------|-------------|
| `--project` | Project name — must match a folder under `omniforge/projects/` |
| `--ticket` | Ticket ID (e.g. `T-001`) |
| `--auto` | Skip gate approval checks; advance through all stages automatically |
| `--force-stage` | Skip all stages before `<stage>` (used to resume from a rollback point) |

### `forge approve` — approve a gate stage

```bash
PYTHONPATH=omniforge/runner python omniforge/runner/forge.py approve \
  --ticket <ticket_id> \
  --stage  <stage> \
  [--by "Approver Name"]
```

Records the approval in `runs/board.json` so the next `forge run` can advance past the gate.

### `forge status` — inspect a ticket

```bash
PYTHONPATH=omniforge/runner python omniforge/runner/forge.py status --ticket <ticket_id>
```

Prints a YAML dump of the ticket's current board state (status, stage, approvals, history).

### `forge list` — list all tickets

```bash
PYTHONPATH=omniforge/runner python omniforge/runner/forge.py list
```

Prints a summary line for each ticket: `<ticket_id>  [<project>]  <status>`.

---

## 8) Viewer UI (Dashboard)

Start the viewer:

```bash
PYTHONPATH=. python omniforge/viewer/app.py
# Listening on http://127.0.0.1:5055
```

### HTTP routes

| Method | Route | Template / Response | Description |
|--------|-------|---------------------|-------------|
| `GET` | `/` | `index.html` | Dashboard: ticket table, Create Ticket form, Worker Loop card |
| `GET` | `/ticket/<id>` | `ticket.html` | Ticket detail: status, run pipeline, gate approval, workspace editor, history, runs list |
| `GET` | `/ticket/<id>/run/<ts>` | `run.html` | Run detail: per-stage logs and artifacts for one timestamped run |
| `GET` | `/ticket/<id>/run/<ts>/stage/<stage>/log` | `<pre>` text | Raw stage log (tail 400 lines by default; `?tail=N` to override) |
| `GET` | `/ticket/<id>/run/<ts>/stage/<stage>/artifact/<name>` | `<pre>` text | Raw artifact file content |
| `GET` | `/ticket/<id>/workspace-diff` | `diff.html` | Unified diff of current workspace vs last run artifact |
| `GET` | `/ticket/<id>/diff` | `diff.html` | Unified diff of `run_report.md` between two runs |
| `GET` | `/playbook/<name>` | `playbook.html` | Read-only view of sdlc_stages, rollback_rules, or company_charter |
| `POST` | `/ticket/create` | redirect | Create a new ticket on the board |
| `POST` | `/ticket/<id>/run` | redirect | Spawn `forge.py run` as a detached background process |
| `POST` | `/ticket/<id>/approve` | redirect | Approve a gate stage (updates `board.json`) |
| `POST` | `/ticket/<id>/workspace/save` | redirect | Save a workspace document (intake/plan/design/research) |
| `GET` | `/api/ticket/<id>/workspace` | JSON | Return workspace file contents for all stages |
| `GET` | `/api/ticket/<id>/run/<ts>/stage/<stage>/tail` | JSON | Tail stage log for live polling (`?tail=120`) |
| `GET` | `/api/projects` | JSON | List available projects (folders under `omniforge/projects/`) |
| `POST` | `/worker/start` | redirect | Spawn the unattended worker as a detached subprocess |
| `POST` | `/worker/stop` | redirect | Signal the worker to stop (writes `running: false` to state file) |
| `GET` | `/api/worker/status` | JSON | Live worker status reconciled against OS PID |
| `GET` | `/worker/log` | `<pre>` text | Tail `runs/worker.log` (default 400 lines; `?tail=N` to override) |

### Dashboard (`/`) capabilities

- **Create Ticket form** — select a project from a live dropdown (populated via
  `/api/projects`), optionally supply a ticket ID, and submit to create a new `created`
  ticket on the board.
- **Worker Loop card** — shows a live status badge (🟢 Running / 🔴 Stopped) that auto-
  refreshes every 5 seconds by polling `/api/worker/status`. Provides **▶ Start**, **⏹ Stop**,
  and **📋 Log** buttons.
- **Ticket table** — lists all tickets sorted by priority (running/failed first, delivered
  last) with columns: Ticket ID, Project, Status, Stage, Last Passed Stage, Run Directory.

### Ticket detail (`/ticket/<id>`) capabilities

- **Run Pipeline form** — trigger `forge.py run` (with optional `--auto` checkbox and
  optional `--force-stage` override) as a non-blocking detached subprocess.
- **Approve Gate form** — record a stage approval by name directly in the browser.
- **History panel** — chronological log of all events (created, run_started, stage_passed,
  stage_failed, paused, delivered) with timestamps and failure reasons.
- **Playbooks panel** — links to read-only views of `sdlc_stages.md`, `rollback_rules.md`,
  and `company_charter.md`.
- **Workspace editor** — tabbed editor for the four pre-run documents (intake, plan, design,
  research). Files are saved to `runs/work/<ticket_id>/` and snapshotted into the run folder
  as required artifacts when the stage executes. A green dot indicates a file has content.
- **Runs table** — lists all timestamped run folders with links to the run detail page and a
  diff comparison control (available when two or more runs exist).

---

## 9) Unattended Worker Loop

The worker (`omniforge/viewer/worker.py`) is a standalone Python script that processes the
ticket backlog automatically — one ticket at a time, no human needed once started.

### Starting and stopping

The worker is designed to be started and stopped from the viewer dashboard, but can also be
run directly:

```bash
# Via the dashboard (recommended)
# Click ▶ Start on the Worker Loop card at http://127.0.0.1:5055

# Directly from the terminal
PYTHONPATH=omniforge/runner python omniforge/viewer/worker.py
```

The Flask `POST /worker/start` route spawns the worker as a detached subprocess
(`subprocess.Popen` with `CREATE_NEW_PROCESS_GROUP` on Windows). A no-op guard checks the
PID in `runs/worker.state.json` before spawning to prevent double-starts.

To stop: click **⏹ Stop** in the UI, or send `POST /worker/stop`. This writes
`{"running": false}` to `runs/worker.state.json`. The worker reads this file at the top of
every loop iteration and exits cleanly.

### State files

| File | Purpose |
|------|---------|
| `runs/worker.state.json` | Worker lifecycle state: `running`, `pid`, `started_at`, `last_tick` |
| `runs/worker.log` | All worker activity: ticket selection, forge commands, output forwarding, stop events |

Both files are git-ignored (`runs/*.json`, `runs/*.log`).

### Ticket selection rules

Each loop iteration the worker calls `_next_ticket()`, which returns the **first** ticket in
board insertion order where `_is_runnable()` is `True`.

**Skip conditions** (ticket is NOT processed):

| Status | Reason |
|--------|--------|
| `running` | Already being executed by another process |
| `paused_at_*` | Waiting for human gate approval |
| `delivered` | Completed successfully — no further work needed |

**Run conditions** (ticket IS processed):

| Status | Behavior |
|--------|----------|
| `created` | Fresh ticket — run from the first configured stage |
| `pending` | Queued ticket — run from the first configured stage |
| `failed_at_<stage>` | Previously failed — resume from `rollback_to` via `--force-stage` |

For `failed_at_*` tickets that have a `rollback_to` field set, the worker automatically
appends `--force-stage <rollback_to>` to the forge command so the run resumes at the correct
rollback point rather than restarting from scratch.

### Worker loop behavior

```
while running:
    read runs/worker.state.json → if running == false: exit
    write last_tick timestamp to state file
    read runs/board.json
    find first runnable ticket
    if found:
        build forge command (python forge.py run --project … --ticket … [--force-stage …])
        run forge synchronously (subprocess.run, stdout forwarded to worker.log)
        sleep 1s
    else:
        sleep 5s  (POLL_INTERVAL — no runnable tickets found)
```

The worker runs `forge.py` **synchronously** (blocking `subprocess.run`), ensuring only one
ticket is in flight at any time. All forge stdout is captured and forwarded line-by-line to
`runs/worker.log` with the ticket ID as a prefix.

### Viewing worker logs

```bash
# In browser (tailed to last 400 lines by default)
http://127.0.0.1:5055/worker/log

# Tail from terminal
tail -f runs/worker.log
```

---

## 10) Project Configuration Reference

### `manifest.yaml` structure

```yaml
name: <project_name>
description: "Human-readable description"
repo_root: "../../<relative-or-absolute-path>"  # working directory for stage commands

stages:
  intake:
    - "shell command"                # plain string
  implement:
    - cmd: "shell command"           # dict with optional cwd override
      cwd: "relative/to/repo_root"

asserts:
  implement:
    - type: file_exists
      path: "relative/to/repo_root/file.ext"
    - type: json_has_keys
      path: "web/output.json"
      keys: ["key1", "key2"]
    - type: json_array_min_length
      path: "web/output.json"
      key: "categories.SomeKey"   # dot-path traversal
      min: 1

artifact_folders:
  - web/
  - data/

serve_command: "php -S localhost:8080 -t web/"
```

### `gates.yaml` structure

```yaml
pause_at:
  - design          # runner pauses here until approved
  - test
  - deliver

rollback:
  implement: design   # if implement fails, roll back to design
  test: implement
  deliver: test

escalation_threshold: 2   # escalate one further stage upstream after N failures
```

To add a new project: create `omniforge/projects/<name>/manifest.yaml` and `gates.yaml`
following the structure above. The project will appear automatically in the viewer's
Create Ticket dropdown.

---

## 11) Board & State Files

All runtime state lives under `runs/` (git-ignored).

### `runs/board.json`

A flat JSON object keyed by ticket ID. Each ticket record contains:

```json
{
  "T-001": {
    "ticket_id": "T-001",
    "project": "omnidigest",
    "status": "paused_at_design",
    "stage": "design",
    "run_dir": "/path/to/runs/T-001/20260407T120000",
    "started_at": "20260407T120000",
    "last_passed_stage": "plan",
    "approvals": { "design": true },
    "approvals_meta": { "design": { "by": "Chris", "at": "20260407T121500" } },
    "rollback_to": null,
    "rollback_counts": { "implement": 1 },
    "history": [
      { "event": "created", "timestamp": "20260407T110000", "project": "omnidigest" },
      { "event": "run_started", "timestamp": "20260407T120000", "project": "omnidigest" },
      { "event": "stage_passed", "stage": "intake", "timestamp": "..." },
      { "event": "paused", "stage": "design", "timestamp": "..." }
    ]
  }
}
```

**Ticket status values:**

| Status | Meaning |
|--------|---------|
| `created` | Just created, not yet run |
| `pending` | Queued for processing |
| `running` | Actively being processed by forge |
| `paused_at_<stage>` | Awaiting gate approval at `<stage>` |
| `failed_at_<stage>` | Stage `<stage>` failed; `rollback_to` is set |
| `delivered` | All stages passed; ticket is complete |

### `runs/work/<ticket_id>/`

Editable workspace directory. The viewer's workspace editor writes files here:

- `intake.md`, `plan.md`, `design.md`, `research.md`

These are snapshotted into the run's evidence folder by `copy_workspace_to_run()` before the
stage loop starts, satisfying the artifact requirement for early stages without requiring
shell commands to generate them.

### `runs/<ticket_id>/<timestamp>/`

Immutable run evidence. One folder per execution attempt:

- `run_report.md` — Markdown summary table of all stages run, their pass/fail results,
  and next-step instructions if paused or failed.
- `<stage>/stage.log` — combined stdout+stderr for all commands in that stage.
- `<stage>/<artifact>.md` — required artifact produced by the stage.

---

## 12) Running Tests

```bash
python -m pytest tests/ -v
```

`conftest.py` adds both the repository root and `omniforge/runner/` to `sys.path` so all
tests can import `omniforge` package modules and the runner's adapter sub-modules without
installing the package.

Test files:

| File | What it covers |
|------|----------------|
| `tests/test_forge.py` | `run_project()`, stage logic, gate enforcement, rollback, artifact checking, assertions |
| `tests/test_local_board.py` | `LocalBoard` adapter: upsert, get, list, approve_stage, history |
| `tests/test_worker.py` | `_is_runnable()`, `_next_ticket()`, `_forge_cmd()` (including `--force-stage` for failed tickets), state file round-trips |

---

## 13) Using with LLMs / OpenAI

OmniForge Labs is designed to be **the grounding corpus for an AI assistant** operating as
one of the named team roles. The documents in this repo are the "source of truth" for what
the LLM should know and how it should behave.

### Recommended reading order (priority)

Feed documents to the model in this order for maximum context:

1. `omniforge/projects/<project>/manifest.yaml` — **what we are building** (stage commands,
   artifact requirements, assertions)
2. `omniforge/projects/<project>/gates.yaml` — **what must be true** at each gate
3. `omniforge/playbooks/sdlc_stages.md` — **how to proceed** through the pipeline
4. `omniforge/playbooks/rollback_rules.md` — **how to fail safely**
5. `omniforge/charter/company_charter.md` — **why and how we decide**
6. `omniforge/charter/roles/<role>.md` — **how to behave** as a specific team member
7. `omniforge/runner/forge.py` — **actual operational logic** (authoritative ground truth)
8. `runs/board.json` — **current live state** of all tickets (if available)

### Role assignment

When asking the LLM to act as a specific role, include the role's `.md` file as the system
prompt or prepend it to the conversation. Each role file defines:
- What the role is responsible for
- What decisions they own
- What artifacts they must produce at each stage

### Expected LLM behavior

When grounded against this repo, the model should:

- Propose work outputs that match the **required artifact** for the current SDLC stage.
- Speak in the role voice when given a role assignment (Kade speaks about architecture;
  Quinn speaks about test strategy; Ember speaks about delivery readiness).
- When uncertain, identify what information is missing from the manifest or gates and
  propose specific clarifying questions rather than guessing.
- Default to **rollback/safety rules** when a stage is risky or ambiguous.
- Check `runs/board.json` for current ticket state before proposing the next action.

### Single-sentence intent (copy-paste for LLM prompts)

> *OmniForge Labs is a governance-driven SDLC orchestration framework that executes project
> manifests through an eight-stage pipeline enforced by quality gates, required artifacts, and
> rollback rules, recording all evidence in timestamped run folders via a pluggable board
> adapter (local JSON by default).*

---

## 14) Glossary

| Term | Definition |
|------|-----------|
| **Ticket** | A unit of work identified by an ID (e.g. `T-001`), bound to a project, progressing through the SDLC pipeline |
| **Stage** | One of the eight named phases: intake, plan, design, research, implement, test, integrate, deliver |
| **Gate** | A stage where execution pauses and requires an explicit human approval before continuing |
| **Artifact** | A required Markdown file that a stage must produce to prove it completed successfully |
| **Board** | The shared state store for all tickets; the local board is `runs/board.json` |
| **Manifest** | A project's `manifest.yaml` — defines what shell commands to run at each stage and what assertions to check |
| **Gates config** | A project's `gates.yaml` — defines which stages are client gates and where to roll back on failure |
| **Rollback** | When a stage fails, the ticket status is set to `failed_at_<stage>` and `rollback_to` points to an earlier stage to retry from |
| **Escalation** | After `escalation_threshold` rollbacks to the same stage, the runner automatically rolls back one stage further upstream |
| **Workspace** | Editable pre-run documents (intake, plan, design, research) under `runs/work/<ticket_id>/` that are snapshotted into run evidence |
| **Worker** | The unattended background process (`worker.py`) that polls the board and processes runnable tickets automatically |
| **Adapter** | A pluggable board backend (e.g. `LocalBoard`, `GitHubProjects`) that the runner interacts with via a consistent interface |
| **Run** | One execution attempt for a ticket, stored under `runs/<ticket_id>/<timestamp>/` with per-stage logs and artifacts |

---

*Last updated: 2026-04-07. Reflects merged PR #2 (unattended worker loop).*