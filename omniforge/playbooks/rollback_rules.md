# OmniForge Labs — Rollback Rules Playbook

## Principle

When a gate fails, the runner **routes back** to the correct upstream stage rather than asking for a blind code fix.  This preserves traceability and prevents compounding errors.

> ⚠️ Never advance a ticket past a failed gate.  Rollback first.

---

## Default Rollback Map

| Failing Stage | Roll Back To | Reason |
|---------------|-------------|--------|
| `plan`        | `intake`    | Requirements were unclear or incomplete. |
| `design`      | `plan`      | Work breakdown doesn't support the proposed design. |
| `research`    | `design`    | Research revealed an incompatibility requiring a design change. |
| `implement`   | `design`    | Implementation is architecturally drifted or blocked. |
| `test`        | `implement` | Tests fail due to implementation bugs (most common). |
| `integrate`   | `implement` | Integration failure is usually a code or config issue. |
| `deliver`     | `test`      | Delivery bundle is broken; re-validate tests before re-packaging. |

---

## Escalation Path

If rolling back to `implement` does not resolve the issue after **two attempts**, escalate:

1. Roll back to `design` — Kade re-evaluates.
2. If still unresolved, roll back to `intake` — Rowan rewrites acceptance criteria with the client.

The runner tracks `rollback_count` per ticket.  At count ≥ 2 on the same stage, it automatically escalates to the next upstream stage.

---

## Rollback Procedure

1. Runner sets ticket `status` to `failed_at_<stage>` on the board.
2. Runner records `rollback_to: <stage>` on the board.
3. Runner prints rollback notice with log path.
4. On next `forge run`, execution resumes from the rollback stage (not from scratch).

---

## Override

A client may override a rollback and force-advance with:

```bash
python forge.py run --project <name> --ticket <id> --force-stage <stage>
```

This is logged on the board as a `force_override` event and should be used sparingly.

---

## Per-Project Overrides

Projects may define custom rollback targets in `gates.yaml`:

```yaml
rollback:
  test: implement        # default
  integrate: design      # project-specific: integration failures need redesign
  deliver: test
```
