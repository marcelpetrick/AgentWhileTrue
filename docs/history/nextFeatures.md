<!--
SPDX-FileCopyrightText: 2026 Marcel Petrick

SPDX-License-Identifier: GPL-3.0-or-later
-->

# Next features

Implement in this order, with one versioned feature commit per step. Preserve
the existing policy, identity, quota freshness, action lifecycle and input lock.
These additions must never grant authorization or log terminal contents.

## 1. Explain resume decisions

Completed in 0.37.0: `d` toggles details and `[` / `]` navigate sessions.

- Add an optional dashboard detail view with per-session navigation.
- Show the latest actual policy decision, observation time, recognized pattern
  and state, quota source/age/freshness, exhausted windows, and retry/grace time.
- Label missing decisions and stale observations explicitly. Display timing as
  a next check or earliest candidate, never a promise of continuation.
- Test absent/stale quota, refusal explanations, and view controls using fakes.

## 2. Save presentation preferences (proposal 5)

Completed in 0.38.0: interactive changes are saved to `preferences.json`.

- Persist theme, history length and display-panel visibility in an owner-only,
  atomically replaced local preferences file.
- Validate a versioned allowlist; malformed, missing or unsupported files use
  defaults. A write failure must leave the dashboard usable and be visible.
- Never persist mode, policy, account information, selected sessions, pause,
  process identity, or authorization. Configuration controls scan intervals.
- Test round trips, malformed data, permissions and excluded fields.

## 3. Operational summaries (proposal 6)

Completed in 0.39.0: `summary --days 1|7` aggregates retained events. New
redacted interval events batch consecutive observations; gaps are excluded.

- Add a read-only day/week report of sent continuations, verified successes,
  failures and refusals from retained structured event logs.
- Include measured blocked time only where observations support it; identify
  incomplete coverage and gaps rather than inventing elapsed supervision.
- Aggregate existing redacted events, including rotated logs, without terminal
  reads, provider requests, or extra sensitive persistence.
- Test time boundaries, rotated/malformed records and lifecycle counting.

## 4. Responsive dashboard (proposal 3)

Completed in 0.40.0: narrow cards, wrapped content, height-bounded viewports,
`j` / `k` and `g` / `G` navigation, and automatic focus for opened panels.

- Keep the wide table where it fits and use readable session cards for narrow
  windows. Respect terminal width and height, including styled output.
- Add viewport scrolling so sessions, details, help and retained history remain
  accessible on short terminals. Preserve a visible navigation hint.
- Keep non-interactive reports complete and ANSI-free.
- Test narrow/wide layouts, small heights, scrolling, resizing and long labels.

## Delivery and review

- Commit this plan before implementation; update completion notes as work lands.
- Every feature/fix commit bumps the version and adds the newest changelog entry.
- Before every commit run Ruff lint/format checks, ShellCheck, pytest and
  `git diff --check`. Use deterministic tests; do not send live terminal input.
- Finish with the local pipeline, read-only live Konsole adapter check where
  available, simulations, and a self-review of the entire change against its
  starting commit. Fix material findings and repeat relevant verification.
- Commit all intended work locally. No push or release tag is requested.

## Final review and verification — 2026-09-10

Base: master @ `2ccd8c7`   Head: `ae537b9`

Files changed: 21   +1656 / -69 lines

The review follows the `reviewBranch` Code and Architecture criteria over the
explicit pre-task baseline. Work was committed directly on master, so comparing
HEAD with master itself would omit all requested changes.

### Findings

No unresolved Code or Architecture findings in the final implementation.
No critical or high-severity findings remain. Review-driven fixes were committed:

- `c00586e`: malformed large JSON integers and unconvertible local timestamps
  could crash startup/reporting; regression tests reproduce both failures.
- `25c221c`: cached pre-pause observations could seed measured time, and string
  concatenation could merge similar measurement identities; regression tests
  now verify fresh observations and distinct session/process tuples.

The review traced preference loading and saving, final supervisor outcomes,
revalidation/verification display metadata, interval sampling and log parsing,
viewport rendering, and CLI keyboard integration. Policy authorization, input
actions, process revalidation and the single-instance lock remain independent
of presentation preferences and reports.

### Verification

- Required pre-commit gates passed for every commit.
- Final pytest: 424 passed, one opt-in live test skipped in the ordinary run.
- Separate live Konsole adapter check: one passed; no continuation sent.
- `./localPipeline.sh`: PASS, including coverage, all 12 safety simulations,
  wheel/sdist build and isolated installation of version 0.40.2.
- Installed command and compatibility alias passed version/simulation smoke
  checks; installed diagnostics and day/week summary commands also passed.
- Direct `doctor`: exit 0. Another watcher holds the input lock; it was left
  running. No deployment, push or tag was performed.
- End-to-end fake-terminal navigation verifies detail/help focus, scrolling
  back after an end jump, viewport height, and zero terminal input.

### Verdict

The four requested features are implemented, reviewed and verified for local
use. The separate genuine provider-reset acceptance gate in
[../OPEN_ISSUES.md](../OPEN_ISSUES.md) remains open; these
presentation/reporting tests do not claim to close it.
