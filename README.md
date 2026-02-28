# OmniForge Labs

An autonomous software shop powered by named AI role bots, a structured SDLC workflow, local test execution, and client-gated review periods.

## Concept

OmniForge Labs coordinates six prompt-driven roles through a strict eight-stage pipeline.  A local runner (`forge.py`) executes commands, captures logs, and updates a JSON ticket board — LLMs decide what to do, the runner proves it works.

| Role | Handle | Owns |
|------|--------|------|
| PM / Delivery Lead | Rowan | Stages, gates, momentum |
| Architect | Kade | Design, boundaries, NFRs |
| Research | Nyx | Options survey, version/CVE checks |
| Dev Lead | Vega | Commits, implementation |
| QA / Test | Quinn | Test plan, execution, evidence |
| Release / Ops | Ember | Packaging, runbook, delivery bundle |

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Run the OmniDigest project through all SDLC stages (auto-approve gates)
PYTHONPATH=omniforge/runner python omniforge/runner/forge.py run \
  --project omnidigest --ticket T-001 --auto

# Check ticket status
PYTHONPATH=omniforge/runner python omniforge/runner/forge.py status --ticket T-001

# List all tickets
PYTHONPATH=omniforge/runner python omniforge/runner/forge.py list
```

## Repository Layout

```
omniforge/
  charter/
    company_charter.md        ← mission, principles, role table
    roles/
      rowan_pm.md             ← PM / Delivery Lead prompt charter
      kade_architect.md       ← Architect prompt charter
      nyx_research.md         ← Research prompt charter
      vega_dev.md             ← Dev Lead prompt charter
      quinn_qa.md             ← QA / Test prompt charter
      ember_release.md        ← Release / Ops prompt charter
  playbooks/
    sdlc_stages.md            ← eight-stage SDLC with owners and gate rules
    rollback_rules.md         ← rollback map + escalation logic
  projects/
    omnidigest/
      manifest.yaml           ← build/test/serve commands per stage
      gates.yaml              ← pause_at stages + rollback targets
  runner/
    forge.py                  ← CLI orchestrator (python forge.py run …)
    adapters/
      local_board.py          ← JSON ticket board (MVP tracker)
      github_projects.py      ← GitHub Issues adapter (stub, future)
runs/                         ← execution logs and board.json (git-ignored)
tests/
  test_local_board.py
  test_forge.py
```

## SDLC Stages

`intake → plan → design ⛔ → research → implement → test ⛔ → integrate → deliver ⛔`

Stages marked ⛔ are **client gates** — the runner pauses for explicit approval.  Pass `--auto` to skip interactive prompts (useful in CI or scripted pipelines).

## Running Tests

```bash
python -m pytest tests/ -v
```

## Tracking

Tickets are stored in `runs/board.json`.  Each ticket records status, last passed stage, run directory, rollback counts, and timestamps.  A GitHub Projects adapter stub is available in `runner/adapters/github_projects.py` for future integration.