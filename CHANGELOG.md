# Changelog

## 0.1.0 — Experimental

- Self-contained eight-stage Python demo with inspectable evidence and a ZIP bundle.
- Process-safe board transactions and atomic JSON replacement on local filesystems.
- Evidence-bound, single-use gate approvals; approval requeues paused tickets.
- Automatic resume from paused/failed stages with earlier run evidence copied forward.
- Configuration validation, meaningful CLI failure exit codes, and collision-resistant run IDs.
- Strict path segments, local-only dashboard requests, CSRF protection, and debugger disabled.
- Bounded worker retries and an explicit runnable-status allowlist.
- Cross-platform regression tests and Windows/Linux CI.

Role charters are prompts, not autonomous agents. GitHub Projects remains a stub.
Rollback selects a retry point; it does not revert source files or side effects.
