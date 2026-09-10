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
