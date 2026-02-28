# OmniForge Labs — SDLC Stages Playbook

## Overview

Every ticket moves through the following eight stages in order.  Each stage has a defined owner, required inputs, required outputs, and a gate outcome (`PASS`, `FAIL`, or `HOLD`).

Stages auto-advance when the previous stage outputs `PASS`.  Three stages are **client-gated** (marked ⛔) and require explicit human approval before advancing.

---

## Stage 1: Intake

**Owner:** Rowan (PM)
**Trigger:** New ticket created on board with a `goal` and `constraints`.

**Inputs**
- Raw requirement from the client
- Constraints (language, runtime, no-Composer, etc.)

**Outputs**
- Refined goal statement (one sentence)
- Success criteria (measurable)
- Out-of-scope list
- Rowan gate recommendation

**Gate:** Auto-advance on `PASS`.

---

## Stage 2: Plan

**Owner:** Rowan (PM)

**Inputs**
- Intake output

**Outputs**
- Work breakdown (milestones per stage)
- Stage checklist with acceptance criteria
- Risk log

**Gate:** Auto-advance on `PASS`.

---

## Stage 3: Design ⛔ (client gate)

**Owner:** Kade (Architect)

**Inputs**
- Plan output

**Outputs**
- Component diagram
- Data flow description
- Dependency list with versions
- Non-functional requirements
- Risk list

**Gate:** **Pause for client approval.**  Advance only on explicit `PASS`.

---

## Stage 4: Research

**Owner:** Nyx (Research)
**Note:** Optional — skip if no new technology or external dependencies involved.

**Inputs**
- Design output

**Outputs**
- Options comparison table
- Version / compatibility notes
- Security / CVE flags

**Gate:** Auto-advance on `PASS`.  Flag `HOLD` if a significant risk is found; route to Kade for design revision.

---

## Stage 5: Implement

**Owner:** Vega (Dev Lead)

**Inputs**
- Design output (and Research output if applicable)

**Outputs**
- Ordered commit plan
- Files changed
- How-to-run instructions

**Gate:** Auto-advance on `PASS`.

---

## Stage 6: Test ⛔ (client gate)

**Owner:** Quinn (QA)

**Inputs**
- Implementation output
- Acceptance criteria from Plan

**Outputs**
- Test plan
- Test execution logs
- Pass/fail evidence

**Gate:** **Pause for client approval.**  On `FAIL`, rollback to `implement`.

---

## Stage 7: Integrate

**Owner:** Vega + Quinn (joint)

**Inputs**
- Passing test stage

**Outputs**
- End-to-end run log
- Glue / integration check results

**Gate:** Auto-advance on `PASS`.  On `FAIL`, rollback per `rollback_rules.md`.

---

## Stage 8: Deliver ⛔ (client gate)

**Owner:** Ember (Release)

**Inputs**
- Passing integration stage

**Outputs**
- Versioned artifact bundle
- `RUNBOOK.md`
- `RELEASE_NOTES.md`

**Gate:** **Pause for client approval.**  On `PASS`, ticket is closed as `delivered`.

---

## Ticket Template

```markdown
## Goal
<one sentence>

## Success Criteria
- [ ] ...

## Constraints
- ...

## Stage Checklist
- [ ] Intake
- [ ] Plan
- [ ] Design      ⛔ client gate
- [ ] Research
- [ ] Implement
- [ ] Test         ⛔ client gate
- [ ] Integrate
- [ ] Deliver      ⛔ client gate

## Commands to Validate
- Build:  <command>
- Test:   <command>
- Serve:  <command>
```
