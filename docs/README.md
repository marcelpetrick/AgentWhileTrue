<!--
SPDX-FileCopyrightText: 2026 Marcel Petrick

SPDX-License-Identifier: GPL-3.0-or-later
-->

# Documentation

## Pick your route

| You want to… | Start here | Success looks like |
| --- | --- | --- |
| Try AWT | [README first flight](../README.md#first-flight) | A read-only watch of intended sessions. |
| Operate unattended | [Flight card](USAGE.md#flight-card-start-arm-recover) | You understand A/y and manual boundaries. |
| Understand the numbers | [This-run scorecard](USAGE.md#this-run-scorecard) | Answers, verified restarts and waits are distinct. |
| Fix a blocker | [Development](DEVELOPMENT.md) | A redacted regression and a complete green gate. |
| Audit trust | [Architecture](ARCHITECTURE.md), then [vision](vision.md) | Every input has a traceable gate. |

Files in [history/](history/) are dated evidence, not instructions to run old
releases, reproduce old metrics or reopen completed work.

- [Usage guide](USAGE.md) — operating the tool: Konsole setup, modes, dashboard,
  configuration, logs, provider specifics, quota bridge, background service.
- [Architecture](ARCHITECTURE.md) — components, data flow, and action gates.
- [Product vision](vision.md) — goals and the conservative safety invariants
  (DANGER 1–20).
- [Implementation plan](PLAN.md) — implemented capabilities, acceptance gate,
  and maintenance flow.
- [Open issues and acceptance work](OPEN_ISSUES.md) — the authoritative backlog.
- [Performance](PERFORMANCE.md) — measured workload and profiling evidence.
- [Development](DEVELOPMENT.md) — quality gate, CI, SBOMs, versioning and
  release artifacts.
- [Completed work](history/) — historical plans and review evidence; not active
  tasks.

Repository entry points remain at the root: `README.md` for users, `AGENTS.md`
for contributor rules, and `CHANGELOG.md` for releases.
