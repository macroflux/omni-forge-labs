# OmniForge Labs

**Experimental v0.1.0** · Local orchestration for evidence-driven, AI-assisted software delivery.

OmniForge turns a project manifest into an inspectable delivery workflow: commands run in
defined stages, required artifacts provide evidence, human approvals control gates, and
failures identify a stage to revisit. A Flask dashboard and background worker sit above
the same local runner and JSON ticket board.

The six named roles are reusable prompt charters. This release does **not** include an
autonomous LLM team, model API integration, or a working GitHub Projects backend.

## Try the self-contained demo

Requires Python 3.10+ on Windows or Linux. Run these commands from the repository root:

```sh
python -m venv .venv
```

Activate the environment: `.venv\Scripts\Activate.ps1` in PowerShell, or
`source .venv/bin/activate` in a POSIX shell. Then:

```sh
python -m pip install -r requirements.txt
python -m omniforge.runner.forge run --project demo --ticket DEMO-001 --auto
python -m omniforge.runner.forge status --ticket DEMO-001
```

The deterministic Python demo runs all eight stages, writes a small JSON result, checks
its content, and creates `deliver/demo-bundle.zip` beneath the ticket's run directory.
It needs no PHP installation, external checkout, credentials, network service, or LLM.
`--auto` explicitly bypasses human gates and records that override in history.

To exercise human review instead:

```sh
python -m omniforge.runner.forge run --project demo --ticket REVIEW-001
python -m omniforge.runner.forge approve --ticket REVIEW-001 --stage design --by Chris
python -m omniforge.runner.forge run --project demo --ticket REVIEW-001
```

Inspect the evidence and repeat approval/resume at `test`, then `deliver`. Gates authorize
the upcoming stage; they are checked **before** its commands run. At the test gate, for
example, review the implementation evidence; approve delivery after inspecting test and
integration evidence. An approval records a local reviewer label, not verified identity.

## Dashboard and worker

```sh
python -m omniforge.viewer.app
```

Open http://127.0.0.1:5055. Create a `demo` ticket, run it, inspect logs and artifacts,
approve gates, edit workspace documents, or start the worker from the dashboard.
Keep one dashboard instance and one worker per checkout. The development server binds to
loopback, rejects nonlocal requests, uses form tokens, and runs with debugging disabled.
It is not an authenticated multi-user service and should not be exposed to a network.

The worker processes created/pending tickets and resumes approved gates. Failed tickets
are eligible while their cumulative recorded stage failures are below three; after that,
inspect and rerun manually. Held, cancelled, unknown, delivered, running, and unapproved
paused tickets are skipped. Stop takes effect between ticket runs; it does not cancel an
active shell command. Run a worker directly with `python -m omniforge.viewer.worker`.

## Workflow and evidence

| Stage | Required artifact | Demo gate |
|---|---|---|
| intake | intake.md | |
| plan | plan.md | |
| design | design.md | Human approval |
| research | research.md | |
| implement | implementation.md | |
| test | test_report.md | Human approval |
| integrate | integration_report.md | |
| deliver | delivery.md | Human approval |

Each configured stage must produce its artifact and pass configured assertions. Empty
command lists still enforce artifacts and gates. Absent stages are deliberately skipped;
`delivered` means all **configured** stages passed, not that an independent auditor has
certified the product. An empty pipeline or unknown stage is rejected.

Approvals are single-use and bind to project configuration, editable Markdown inputs,
and Markdown evidence through the gate. Changed inputs require another approval;
workspace edits restart the normal pipeline. This is not a cryptographic source-code or
binary attestation. A new execution attempt gets a unique run directory; a resumed
attempt copies earlier stage evidence forward without rewriting the preceding run.

Runtime files are local and ignored by Git:

- `runs/board.json`: ticket state and history, protected by process locks and atomic writes.
- `runs/work/<ticket>/`: editable intake, plan, design, and research documents.
- `runs/<ticket>/<run-id>/`: stage logs, artifacts, and `run_report.md`.
- `runs/worker.log` and `runs/worker.state.json`: worker output and lifecycle state.

Use a local filesystem. Network filesystem locking and crash recovery are not supported.
If a runner crashes and leaves `running`, confirm it has stopped before repairing the
ticket state. There is no automatic process lease/recovery service in v0.1.

## Projects and commands

Create `omniforge/projects/<name>/manifest.yaml` and `gates.yaml`; see `projects/demo/`.
Project/ticket IDs begin with a letter or digit and otherwise use letters, digits, `_`, or
`-`, up to 80 characters. The dashboard discovers project directories automatically.

- `stages`: recognized stage names mapped to shell strings, command lists, or `{cmd, cwd}` entries.
- `repo_root`: working directory, absolute or relative to `omniforge/runner/forge.py`.
- `{python}` in command strings expands to the active Python executable; quote it as in the demo.
- `asserts`: per-stage `file_exists`, `json_has_keys`, and `json_array_min_length` checks.
- `pause_at`, `rollback`, and `escalation_threshold`: human gates and retry routing.

Commands receive `FORGE_RUN_DIR`, `FORGE_STAGE_DIR`, `FORGE_TICKET`, and `FORGE_PROJECT`.
Write evidence into `FORGE_STAGE_DIR`. Manifests execute trusted shell commands with your
user's permissions; they are not sandboxed. Inspect a manifest before running it.
`artifact_folders` and `serve_command` are descriptive metadata; the runner does not
automatically package or serve them. A project's delivery command must create its bundle.

`omnidigest` is a separate, optional PHP integration example. Its manifest points to the
author's `C:/dev/omni-feed` checkout; edit that path and provide that application yourself.
It is not the portable quick-start example.

```sh
python -m omniforge.runner.forge list
python -m omniforge.runner.forge run --project demo --ticket REVIEW-001
python -m omniforge.runner.forge run --project demo --ticket REVIEW-001 --force-stage implement
```

A normal rerun resumes from a paused or failed stage. `--force-stage` is an explicit,
logged override that can skip earlier stages. Rollback records where to retry; it does
not undo source changes, deployments, or command side effects. Stage failures return a
nonzero CLI exit status; an intentional gate pause returns zero and is visible on the board.

## Roles and development

| Handle | Prompt charter |
|---|---|
| Rowan | PM and delivery |
| Kade | Architecture |
| Nyx | Research |
| Vega | Implementation |
| Quinn | QA and evidence |
| Ember | Release and operations |

Use `omniforge/charter/roles/` as grounding material for an assistant. The charter and
playbooks describe the larger ambition; this README describes the v0.1 implementation.
The GitHub adapter raises `NotImplementedError` and is not selectable as a live backend.

```sh
python -m pytest -q
```

The included CI workflow is configured for Windows and Linux with Python 3.10 and 3.12. See
[CHANGELOG.md](CHANGELOG.md) for the release scope. Next areas: model/tool integration,
GitHub synchronization, process recovery, stronger evidence validation, and richer delivery checks.

Released under the [MIT License](LICENSE).
