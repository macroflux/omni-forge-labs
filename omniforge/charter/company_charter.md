# OmniForge Labs — Company Charter

## Mission

OmniForge Labs exists to build and deliver software projects autonomously through a coordinated team of AI-powered role bots, structured workflows, local test execution, and defined review gates.  The goal is repeatable, traceable delivery — from a single sentence of intent to a working, tested, deployable artifact.

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
