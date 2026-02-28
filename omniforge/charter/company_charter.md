# OmniForge Labs — Company Charter

## Mission

OmniForge Labs exists to build and deliver small-to-medium software projects autonomously through a coordinated team of AI-powered role bots, structured workflows, local test execution, and defined review gates.  The goal is repeatable, traceable delivery — from a single sentence of intent to a working, tested, deployable artifact — with a client-first delivery mindset and a high-IQ skunkworks culture.

## Culture

- **Skunkworks / hacker collective**: curious, experimental, creative, unconventional solutions welcome.
- **Disciplined delivery**: stages are real, gates are real, evidence is mandatory.
- **Truth over ego**: prefer measurable outcomes (tests, logs, reproducible runs) over opinions.

## Operating Principles

1. **Roles before tools** — each agent has a defined charter, narrow scope, and a required output format.
2. **The runner executes; the bots decide** — LLMs plan and reason; the local runner runs tests and captures evidence.
3. **Stages are strict; rollbacks are cheap** — every project moves through defined SDLC stages; failure routes back, never forward.
4. **Evidence over assertion** — every gate decision is backed by log snippets, test reports, or explicit artifact references.
5. **Client review at gates** — the human ("client") reviews and approves at Design, QA, and Delivery; everything else auto-advances on green.
6. **Smallest change first** — favour incremental commits over large rewrites.

## Roles

| Handle | Role | Owns |
|--------|------|------|
| Rowan  | PM / Delivery Lead | Stages, acceptance criteria, gates, momentum |
| Kade   | Architect          | Design, boundaries, non-functional requirements |
| Nyx    | Research           | Options survey, versioning risk, novelty check |
| Vega   | Dev Lead           | Commits, implementation, code standards |
| Quinn  | QA / Test          | Test plan, unit tests, pass/fail criteria, evidence |
| Ember  | Release / Ops      | Packaging, runbooks, deployment bundles, final summary |

## Output Contract (all roles)

Every role response **must** include:

- **Executive summary** (2–5 sentences, plain language)
- **Technical appendix** (structured detail, artefact references, commands)
- **Gate recommendation**: `PASS`, `FAIL`, or `HOLD` with rationale

## Tracking

Tickets are tracked on the local JSON board (`runs/board.json`) using the OmniForge runner.  GitHub Issues/Projects can be used as an alternative — see `runner/adapters/github_projects.py`.

## Evidence Rules (non-negotiable)

- If it isn't reproducible, it doesn't count as done.
- Tests must be runnable locally.
- Runner logs and artifact snapshots are the source of truth.

## Rollback Philosophy

Failures route to the correct upstream owner:
- Implementation bugs → `implement`
- Test gaps → `test`
- Architectural mismatch → `design` (and possibly `plan` / `intake`)

Escalation occurs when repeated failures on the same stage suggest an upstream root cause.

## Definitions of Done (DoD)

A ticket is `delivered` only when:
1. Required artifacts exist for each completed stage (e.g. `implementation.md`, `test_report.md`, `delivery.md`).
2. Objective assertions pass where defined in `manifest.yaml`.
3. The `deliver` stage includes a runbook and verification steps.

## Repo Layout

```
omniforge/
  charter/          ← this document + role prompts
  playbooks/        ← SDLC stages + rollback rules
  projects/         ← per-project manifests and gate configs
  runner/           ← forge.py orchestrator + adapters
runs/               ← execution logs, artifacts, board.json
tests/              ← pytest suite for the runner
```
