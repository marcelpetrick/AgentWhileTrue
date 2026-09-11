<!--
SPDX-FileCopyrightText: 2026 Marcel Petrick

SPDX-License-Identifier: GPL-3.0-or-later
-->

# Changelog

All notable changes to Agent While True are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and
the project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
While the major version is `0`, the minor version is bumped for every feature
increment and the patch version for fixes.

## [0.41.1] - 2026-09-11

### Fixed

- Select the freshest valid windowed Codex quota event across open rollouts
  in the selected process profile, instead of trusting file-descriptor order.
- Reject malformed quota percentages and implausibly future observations as
  authorization evidence; keep reads bounded and account/profile state isolated.

## [0.41.0] - 2026-09-10

### Added

- Enforce 91% combined statement/branch coverage with additional identity,
  process, status transport and terminal cleanup failure-path tests.
- Annotate repository files with SPDX metadata and enforce REUSE compliance.
- Generate and validate SPDX 2.3 and CycloneDX 1.6 runtime/release-artifact SBOMs.
- Verify a freshly extracted source archive and install wheels outside the
  checkout; retain profiles, coverage and SBOMs in CI/release artifacts.
- Audit development/build dependencies in an isolated scheduled CI job.

## [0.40.3] - 2026-09-10

### Fixed

- Redraw presentation keys without multiplying terminal and quota scans; keep
  explicit rescans and immediate pre-input revalidation.
- Avoid Unicode database calls for ASCII layout, preserving wide and combining
  character behavior. Add reproducible synthetic profiles and operation-count
  regressions alongside current read-only live measurements.

## [0.40.2] - 2026-09-10

### Fixed

- Keep measurement identities separate even when session/PID suffixes coincide,
  and reject cached pre-pause evidence when starting a new sampled interval.

## [0.40.1] - 2026-09-10

### Fixed

- Reject oversized JSON integers in preferences and unconvertible local log
  timestamps without crashing dashboard startup or operational reports.

## [0.40.0] - 2026-09-10

### Added

- Responsive session cards below 168 columns and a height-bounded dashboard
  viewport with `j` / `k` scrolling and `g` / `G` top/end navigation.
- Wrap detail, history and help text; preserve cell widths for wide/combining
  characters and remove terminal control sequences from displayed fields.
- Keep navigation visible and focus opened detail/help/history panels without
  restoring selections or changing input policy.

## [0.39.0] - 2026-09-10

### Added

- Read-only `summary --days 1|7` reports retained sends, verified resumptions,
  armed provider waits, failures and refusal episodes across rotated logs.
- Batch sampled supervision intervals to report observed and blocked session
  time without counting pauses, unknown states or observation gaps as coverage.

## [0.38.0] - 2026-09-10

### Added

- Save interactive theme, history length and panel visibility in an owner-only
  atomic preferences file. Invalid files use defaults; failed saves are visible.
- Preferences never restore input mode, authorization, selections or scan timing.

## [0.37.0] - 2026-09-10

### Added

- Dashboard resume explanations (`d`, then `[` / `]`) show the latest outcome,
  observation age, recognized patterns, quota evidence and scheduled checks.
- Preserve the final tick outcome and revalidation/verification observations
  for display without retaining terminal text or changing authorization.

## [0.36.14] - 2026-09-10

### Fixed

- Show 10 history entries by default instead of 5 in the dashboard.

## [0.36.13] - 2026-09-09

### Documentation

- Scoped the recorded status-transport profile to the measured direct path and
  documented that proxy-aware transport performance may differ.

## [0.36.12] - 2026-09-09

### Fixed

- Retained standard-library HTTP(S) proxy handling for provider health checks;
  direct connections use the persistent low-overhead transport.

## [0.36.11] - 2026-09-09

### Documentation

- Added a reproducible local workload profile with before/after CPU, memory,
  context-switch, subprocess, and compressed status-traffic measurements.

## [0.36.10] - 2026-09-09

### Fixed

- Renamed a reserved Mermaid node identifier so GitHub and browser renderers
  display the guarded-resume architecture flow correctly.

## [0.36.9] - 2026-09-09

### Fixed

- Decoupled full Konsole rediscovery from selected-session scans and removed a
  redundant foreground-PID query, sharply reducing idle `qdbus` subprocesses
  while retaining immediate manual rescans and pre-action revalidation.

## [0.36.8] - 2026-09-09

### Fixed

- Provider health workers now reuse one persistent HTTPS connection per status
  service, retaining one-second checks without repeated DNS and TLS setup.

## [0.36.7] - 2026-09-09

### Documentation

- Replaced the historical execution plan with a current implementation,
  acceptance, maintenance, delivery, and deferred-scope roadmap.
- Reduced the machine TODO to the genuine-reset validation that remains and
  reconciled README setup/examples plus the vision document navigation.

## [0.36.6] - 2026-09-09

### Documentation

- Added a C4-style architecture reference with Mermaid system-context,
  container, component, guarded-resume, lifecycle, and deployment diagrams.

## [0.36.5] - 2026-09-09

### Documentation

- Added the short command sequence for handing the single-instance lock between
  the background service and the interactive TUI.

## [0.36.4] - 2026-09-09

### Removed

- Removed the remaining obsolete peak-hours configuration compatibility and
  current documentation; provider health and actual quota resets remain.

## [0.36.3] - 2026-09-09

### Fixed

- Multi-day effective reset values now use the same conservative upward rounding
  as their per-window countdowns, avoiding contradictory `+3d` and `4d` labels.

## [0.36.2] - 2026-09-09

### Fixed

- Full-auto toggling now requires an uppercase `A`, preventing an easy accidental
  lowercase keypress from enabling terminal input and Codex continuation.

## [0.36.1] - 2026-09-09

### Changed

- Pinned the build and development toolchain to current stable releases:
  setuptools 84.0.0, pytest 9.1.1, pytest-cov 7.1.0, Ruff 0.16.6, and build
  1.6.0.
- Updated the setup-python workflow action to 7.0.0 and the GitHub release
  action to 3.0.3; checkout and artifact upload were already current.

## [0.36.0] - 2026-09-09

### Added

- The interactive `a` key toggles safely between observe and full-auto mode.
  Enabling takes the single-writer lock first and explicitly opts into Codex
  composer continuation; lock contention leaves the watcher read-only.
- The dashboard retains 50 history entries in memory while rendering only the
  selected 5, 10, 20, or 50 rows. Terminal retriggers and their verification
  results remain visible after returning to the dashboard.

### Safety

- Switching to observe updates policy before releasing the input lock. Switching
  to full-auto acquires the lock before policy changes, and every later action
  still passes the normal identity, prompt, quota, policy, and revalidation gate.

## [0.35.0] - 2026-09-09

### Added

- Five-hour and weekly quota meters now each show their own compact reset
  countdown. Durations below 1.5 days use hours; longer durations use days.

## [0.34.2] - 2026-09-09

### Fixed

- Removed configurable peak-hour guesses from the dashboard. Anthropic has
  removed Claude Code's peak-hour limit reduction for Pro and Max accounts, no
  provider publishes a live schedule API, and legacy hint keys are now accepted
  only for configuration compatibility and ignored.

## [0.34.1] - 2026-09-09

### Fixed

- Service health now follows the official Codex API, Claude Code, and Claude API
  component IDs instead of generic OpenAI components or page-wide incidents.
- OpenAI and Anthropic are polled independently once per second through their
  canonical public JSON endpoints, with gzip, ETag revalidation, bounded
  responses, strict status parsing, and `UNKNOWN` on every ambiguity or error.

## [0.34.0] - 2026-09-09

### Changed

- Updated the README's dashboard screenshot to the v0.33.0 interface and kept
  the v0.24.0 screenshot in `media/` as an archival record.

## [0.33.0] - 2026-09-08

### Changed

- Renamed the ambiguous `PROMPT` column to `PROMPT RESET`: it is the reset time
  parsed from the blocking terminal prompt, kept distinct from provider
  `QUOTA RESET`.
- Five-hour and weekly meters now show only used percentage, for example
  `[████░] 84%`, without the redundant remaining percentage.
- Dark, vivid, CGA, and amber now style the complete framed dashboard surface,
  with contrasting section headers and semantic colors for provider, account,
  state, quota, usage, service health, history, and help cells. Plain remains
  completely ANSI-free.

## [0.32.0] - 2026-09-08

### Added

- The dashboard shows cached health for OpenAI Responses/Login and Anthropic
  Claude Code/API using the providers' public Statuspage summaries.
- Health age updates with the TUI refresh while network polling runs in a
  background thread once per second, with a configurable interval.
- Optional provider peak-hour display hints are supported. Defaults explicitly
  say `not published` because neither provider publishes predictive peak-load
  windows suitable for an authoritative built-in schedule.

### Safety

- Status checks never call a model, use account credentials, authorize resume,
  or block the supervisor loop. Missing, malformed, or unreachable status data
  is displayed as `UNKNOWN`.

## [0.31.0] - 2026-09-08

### Added

- Each dashboard row now shows the account tied to that exact process. Codex
  profile homes distinguish the default login from launchers such as
  `codex-dmo`, and the owner-private ID token supplies its display-only email.
- Compact btop-style meters show both used and remaining percentages for the
  five-hour and weekly quota windows.

### Safety

- Account emails and selected profile paths remain memory-only presentation
  data and are never written to logs or persistent state.

## [0.30.8] - 2026-09-07

### Fixed

- Codex continuation text is now sent as an explicit bracketed paste followed
  by Enter. This prevents Codex's 120 ms unbracketed-paste detector from
  swallowing the submit as a composer newline when D-Bus delivers the text as
  a rapid key stream.

### Validation

- Recovered the exact pending `myLastFmPlayer` Codex session by sending a bare
  Enter only after service/session/PID, process identity, TTY, classification,
  policy, same-account quota, and continuation-only draft revalidation.
- Proved the new sequence against Codex CLI 0.153.4 in a disposable live
  session; the bracketed continuation and Enter submitted as one turn.

## [0.30.7] - 2026-09-07

### Fixed

- Codex prompt recognition is restricted to its immediate eight-line composer
  area. A historical limit banner left visible above a completed continuation
  can no longer trigger bounded retries as the screen fingerprint changes.

## [0.30.6] - 2026-09-07

### Fixed

- Each supervisor tick now warms quota for every selected session before making
  its first decision. A blocked Codex tab enumerated before a fresh same-account
  tab can therefore resume on the initial post-start scan instead of scheduling
  itself from its stale rollout.

## [0.30.5] - 2026-09-07

### Fixed

- The one-shot `quota` command warms every live session before rendering, so a
  fresh account-bound Codex observation is shown consistently regardless of
  Konsole enumeration order.

## [0.30.4] - 2026-09-07

### Fixed

- The canonical local/GitHub pipeline now fails when ShellCheck is unavailable,
  runs `git diff --check`, and smoke-tests installed-wheel `doctor`, `status`,
  and `quota` commands alongside both CLI names and every safety simulation.

## [0.30.3] - 2026-09-07

### Fixed

- A blocked Codex session can use a newer quota observation from another live
  session only when both rollouts are positively bound to the same authenticated
  account and rate-limit identity. This breaks the stale-rollout deadlock after
  reset while keeping different or unidentified accounts isolated.

### Safety

- Codex account IDs are reduced to memory-only SHA-256 keys and are never
  displayed, logged, persisted, or inferred when the owner-private auth file
  cannot be validated.

## [0.30.2] - 2026-09-07

### Fixed

- Codex's tested usage-limit banner may advertise Pro and paid credits beside
  its free reset time without blocking safe composer continuation after fresh
  provider quota confirmation. The exception applies only to that exact mixed
  banner and cannot activate either paid link.

### Safety

- Out-of-credit, reset-credit, purchase-only, model-downgrade, unknown, and
  stale-quota screens remain fail-closed.

## [0.30.1] - 2026-09-07

### Fixed

- Zone-less provider reset times are interpreted in the machine's local IANA
  timezone even though the supervisor keeps its internal clock in UTC. A Codex
  `3:36 PM` reset in Europe/Berlin therefore remains `15:36`, rather than being
  shifted to `17:36` after display conversion.

## [0.30.0] - 2026-09-07

### Added

- The dashboard now offers five themes: dark, vivid, CGA, amber, and plain.
- The CGA palette uses the classic high-contrast cyan, magenta, white, and black
  terminal aesthetic; amber provides a warm monochrome-inspired alternative.

## [0.29.0] - 2026-09-07

### Added

- Interactive dashboards show the authenticated Codex and Claude account email
  when provider-owned local identity data makes it available.

### Safety

- Account identity is read once for interactive presentation only. Emails are
  never logged, persisted, or rendered by non-interactive/service dashboards;
  malformed, unavailable, or insecurely permissioned identity data is shown as
  unavailable.

## [0.28.1] - 2026-09-07

### Fixed

- The systemd user service now treats the CLI's deliberate signal-handling exit
  code `130` as successful, so an ordinary stop or restart no longer records a
  transient failed result after the lock is released cleanly.

## [0.28.0] - 2026-09-07

### Added

- `fullAutoMode.sh` runs the complete release gate, installs the verified wheel
  with pipx, initializes configuration, requires a passing environment doctor,
  displays live session/quota checks, and then opens the all-session auto-mode
  dashboard with the explicit Codex opt-in.
- `--noRun` performs the same setup and checks without starting the dashboard.

### Changed

- Project metadata and documentation now consistently license Agent While True
  under GPLv3 or later.

### Safety

- An existing input-capable watcher is never stopped or competed with; the
  launcher opens a simultaneous observe-only dashboard when the single-instance
  check reports an existing controller.
- The launcher does not change Konsole, provider, account, subscription, paid,
  reset-credit, or model-quality settings.

### Fixed

- The supplied user service now links to the standalone repository instead of
  its former monorepo location.

## [0.27.4] - 2026-09-07

### Changed

- Agent While True now lives in its own repository with its complete project
  history preserved and the package at the repository root.
- README links, badges, package metadata, and contributor guidance now target
  the standalone repository.
- Quality and release workflows now run from the standalone repository root.
- GPLv3-only licensing is declared in package metadata, linked from the README,
  and included in source and wheel distributions.

## [0.27.3] - 2026-09-07

### Fixed

- The systemd user service now supplies a UTF-8 locale, preventing qdbus6 from
  flooding the journal with one locale warning for every D-Bus call.

### Verified

- New Konsole processes permit scoped D-Bus input while pre-setting processes
  remain safely blocked.
- The installed TUI's refresh, pause, theme, history, help, rescan, and quit
  controls pass against a live read-only pseudo-terminal.
- A persistent auto-mode user service now watches all sessions with the
  explicit Codex-resume policy enabled; paid and model-changing actions remain
  forbidden.

## [0.27.2] - 2026-09-06

### Fixed

- Doctor policy tests no longer inherit the runner's installed qdbus tools.
- Reset display tests now derive the expected local time from the runner's
  timezone instead of assuming Europe/Berlin, keeping the 3.12–3.14 GitHub
  matrix deterministic.

## [0.27.1] - 2026-09-06

### Fixed

- User-facing diagnostics and README examples consistently use the
  `agent-while-true` primary command and Agent While True product name.
- The README now makes clear that Konsole must be restarted after enabling its
  security-sensitive D-Bus API; existing terminal processes cannot reload it.

### Verified

- The complete local pipeline passes with 89% coverage, all safety scenarios,
  package builds, and an isolated wheel install.
- The installed command reads fresh owner-only Claude bridge data, real Codex
  rollout quota, and all current open agent sessions; the live Konsole adapter
  test passes.

## [0.27.0] - 2026-09-06

### Added

- A canonical `localPipeline.sh` runs the Python baseline check, Ruff,
  formatting, ShellCheck, coverage gate, every safety simulation, distribution
  build, isolated wheel install, and both CLI smoke tests.
- Path-filtered GitHub Actions quality and release workflows test Python 3.12
  through 3.14 and publish verified `agentwhiletrue-v*` tags.
- README quality, release, Python baseline, and license badges.

### Changed

- The supplied systemd unit and installation guidance use the primary
  `agent-while-true` command while retaining `agent-watch` compatibility.

## [0.26.0] - 2026-09-06

### Added

- The dashboard can show the recent persisted state/action history. Press `e`
  to hide it and `l` to cycle through 5, 10, 20, or 50 rows.
- The README documents the history file, `logs` command, journal view, and the
  privacy boundary: terminal content is never persisted.

### Changed

- Codex sessions launched through the Node.js shim are presented as `Codex` in
  the dashboard once the child process has been classified.
- Remaining project documentation now consistently uses the Agent While True
  product name.

## [0.25.0] - 2026-09-06

### Fixed

- A thread disappearing between `/proc/<pid>/task` enumeration and reading its
  `children` file no longer crashes long-running discovery. Child inspection
  and per-session classification isolate the same expected process churn.
- Transient empty Codex rate-limit objects no longer replace the most recent
  usable event with `unrecognised-rate-limit-shape`.

## [0.24.0] - 2026-09-05

### Added

- A btop/ollamaFarm-inspired interactive dashboard with semantic colors,
  responsive `+`/`-` refresh control, pause, immediate rescan, theme cycling,
  help overlay and clean quit/cursor restoration.
- Dark, vivid and plain themes; `NO_COLOR` and `--no-color` disable ANSI.

### Changed

- Paused dashboards perform no terminal or quota polling.
- Non-interactive observe mode separates successive scans with a blank line.

## [0.23.0] - 2026-09-05

### Changed

- Python 3.12 is now the explicit minimum in package metadata, contributor
  guidance and Ruff's syntax target. CI covers Python 3.12 through 3.14.

## [0.22.0] - 2026-09-05

### Changed

- The product is now consistently named **Agent While True**, described as an
  agent budget watch and babysitter. The primary installed command is
  `agent-while-true`; `agent-watch` remains a fully compatible alias and the
  established config/state paths remain unchanged.

## [0.21.0] - 2026-09-05

### Added

- Auto mode can arm Claude Code's own `Wait here, then continue automatically`
  choice when the exact tested menu has item 1 visibly selected and fresh quota
  confirms the session window is exhausted.
- The action sends one Down sequence and Enter, revalidates the complete screen
  and process identity first, persists idempotency before sending, and verifies
  Claude's self-healing state afterwards.

### Safety

- Unknown/stale quota, a changed cursor or menu, disabled
  `ALLOW_CLAUDE_AUTO_WAIT`, and every non-exact prompt refuse the menu action.
  The adjacent paid upgrade remains forbidden.

## [0.20.0] - 2026-09-05

### Added

- `scripts/install-claude-bridge.sh` installs the local quota proxy, backs up
  Claude's settings, and safely chains any existing status-line command. It is
  idempotent and never replaces the user's status-line behavior.

## [0.19.0] - 2026-09-05

### Fixed

- Codex quota discovery now walks from Konsole's foreground Node launcher to
  its native child, which is the process that actually owns the session rollout
  descriptor. Live Codex sessions therefore report their real five-hour and
  weekly availability instead of `no-rollout-file`.

## [0.18.0] - 2026-09-05

### Added

- A complete README covering isolated installation, live quota queries, modes,
  Claude status-line integration, the safe background service, troubleshooting,
  simulations and the pre-input safety gate.
- The real Claude limit-menu screenshot documents the prompt the recognizer's
  regression fixture protects.

### Fixed

- Package metadata now identifies GPL-3.0-only, matching the enclosing
  repository license instead of incorrectly claiming MIT.

## [0.17.0] - 2026-09-05

### Added

- Explicit `--all` watchers stay alive with no initial sessions and safely add
  eligible Codex and Claude processes discovered later.
- An observe-only systemd user unit and installer. Automatic terminal input is
  never enabled merely by installing the service.
- Subprocess coverage for Claude quota capture, command chaining, malformed
  input and concurrent status-line writers.

### Fixed

- Claude status-line writes now use unique owner-only temporary files before an
  atomic replace, preventing multiple Claude sessions from racing over one
  shared temporary path.
- The status view no longer advertises unimplemented keyboard shortcuts.

## [0.16.0] - 2026-09-05

### Added

- `agent-watch quota` reports live Codex and Claude availability, source errors,
  usage percentages and reset times without sending terminal input.
- The running status table and observe output show provider quota state beside
  the independently recognised terminal prompt state.
- A regression fixture transcribed from `media/claude_out_of_quota.png` covers
  Claude Code's three-choice limit menu.

### Safety

- The menu's automatic-wait option is not mistaken for an already enabled
  self-resume, and the paid upgrade choice is an explicit automation veto.

## [0.15.0] - 2026-09-05

### Added

- `agent_watch.simulate` and `agent-watch simulate`: twelve runnable safety
  scenarios covering the situations section 40 of the vision requires - reset
  and resume, the agent exiting first, PID reuse, suspend across a reset, a
  scrolled-away banner, a still-spent weekly limit, an unavailable provider, the
  self-healing provider, a duplicated prompt, crash recovery, the Codex opt-in
  and observe mode.
- Each scenario prints the steps it took and the decision made at each one, so a
  person can watch a specific danger play out rather than take the safety
  argument on trust.
- The test suite asserts every scenario, including that the happy path really
  does send a keystroke - a suite that passed by never typing would prove
  nothing.

## [0.14.0] - 2026-09-05

### Added

- `agent_watch.cli`: `run`, `status`, `doctor`, `init`, `config` and `logs`,
  with `--observe` / `--ask` / `--auto`, `--all`, `--once` and `--no-fzf`.
  Running bare runs.
- Running under `sudo` aborts with an explanation unless `--allow-root` is
  given: root is unnecessary, breaks access to the user's session bus, and makes
  an incorrect keystroke more expensive.
- The single-instance lock is taken only by modes that can send input, so a
  read-only watcher can always be started alongside an automatic one.
- `init` writes a commented config; a test asserts the tool can parse back what
  it just wrote.
- `SIGINT` and `SIGTERM` end the loop cleanly and release the lock.

## [0.13.0] - 2026-09-05

### Added

- `agent_watch.ui`: the running status table and the one-line observe-mode
  output. Plain text, no curses - pipe-able, greppable, and readable inside a
  test failure.
- A reset more than a day out renders as `+3d` rather than a bare clock time,
  which would be actively misleading.
- `agent_watch.doctor`: diagnostics for the platform, desktop, privileges,
  qdbus, Konsole D-Bus and session enumeration, both agent CLIs, optional tools,
  the three directories and the single-instance lock - ending with a straight
  answer to the question the user actually has: whether auto mode is safe here.
- Optional tools are reported, never failed; a missing `fzf` is information.

## [0.12.0] - 2026-09-05

### Added

- `agent_watch.picker`: discovery, a built-in numbered multi-select picker, and
  optional `fzf` support that degrades cleanly when `fzf` is absent.
- Only high-confidence agent sessions are preselected, and an ineligible session
  cannot be toggled on at all - with the reason shown next to it, so a refusal
  is visible to the person making the choice.
- A closed stdin ends the picker rather than accepting the preselection;
  silence is not consent.
- Discovery, toggling and rendering are pure functions, so the decision logic is
  tested without a terminal.

## [0.11.0] - 2026-09-05

### Added

- `agent_watch.fsm`: the supervisor - observe, decide, act, verify - and the
  per-session state machine.
- Revalidation before input: `act()` treats the decision as a proposal, re-reads
  the foreground process, identity, session reference and screen, re-runs the
  recognizer and the gate, and cancels on any drift.
- Verification is a state with a deadline rather than a sleep, so one wedged
  session cannot stall the others.
- Suspend and clock-change detection by comparing wall-clock against monotonic
  elapsed time across a tick; a divergence discards every pending schedule and
  forces full revalidation.
- A per-session attempt budget alongside the per-prompt one, so a screen that
  keeps changing cannot mint a fresh budget on every tick.
- A session marked unsafe stays unsafe; a later screen reading cannot quietly
  promote it back.
- `tests/harness.py`: a fake terminal, a fake process table and a clock whose
  wall and monotonic hands move independently, so suspend, PID reuse, process
  swap, wedged terminals and crash recovery are all covered in milliseconds.

## [0.10.0] - 2026-09-05

### Added

- `agent_watch.lock`: an advisory `flock` under `$XDG_RUNTIME_DIR`, so two
  supervisors cannot each correctly decide to press Enter once and between them
  press it twice. Observe mode does not take the lock, so a read-only watcher
  can run alongside an automatic one.
- `agent_watch.state_store`: the action lifecycle
  `PLANNED -> SENT -> VERIFIED|FAILED`, persisted atomically. The record is
  written *before* the keystroke, so a crash in between is read back as "may
  already have been typed" and refuses rather than repeating.
- Writes go through a temporary file, `fsync` and `os.replace`; a half-written
  state file would read back as "nothing has been done yet", which is worse than
  no file at all.
- A corrupt or future-versioned state file starts empty instead of refusing to
  run, and records older than 24 hours are dropped on load.

## [0.9.0] - 2026-09-05

### Added

- `agent_watch.policy`: the resume gate. Fourteen named preconditions, each
  returning a refusal *reason* rather than a bare false, so a log reader can act
  on a refusal instead of guessing at it.
- `Authorization`, grading how strongly the evidence says usage returned:
  `PROVIDER_CONFIRMED` (a fresh quota snapshot, or the provider's own "usage
  limit has reset" affordance) outranks `TIME_ONLY` (a wall-clock reset plus the
  grace period). Auto mode requires the former; ask mode will offer the latter;
  observe mode acts on neither.
- `idempotency_key()`: provider, session, process start time and screen
  fingerprint, so one logical prompt yields at most one action and a restarted
  agent in the same tab counts as a new prompt.
- Every refusal carries `retry_at` when a reset time is known, so a session
  blocked for four hours is not polled every two seconds.
- The gate is handed a `ResumeRequest` and cannot fetch anything itself, so it
  cannot depend on state the caller did not revalidate.

## [0.8.0] - 2026-09-05

### Added

- `agent_watch.quota`: provider quota state, kept separate from terminal state.
- `CodexRolloutSource`: Codex keeps its session rollout `.jsonl` open, so the
  file for a given PID can be located through `/proc/<pid>/fd`; each
  `token_count` event carries a `rate_limits` object with the five-hour window,
  the weekly window and credits. Machine-readable provider state, no TUI
  parsing.
- `ClaudeStatuslineSource`: reads the small document written by the status-line
  proxy, carrying Claude Code's `five_hour` and `seven_day` usage and resets.
- `Availability.UNKNOWN` for anything missing, stale, malformed or broken.
  Unknown never means available.
- Sources are failure-isolated by contract - `snapshot()` never raises - so a
  broken Codex source cannot stop Claude monitoring.
- `next_reset` returns the *last* exhausted window to clear, so a five-hour
  reset cannot unblock a session whose weekly limit is still spent.

## [0.7.0] - 2026-09-05

### Added

- `agent_watch.states`: the `SessionState` and `ActionState` vocabularies.
- `agent_watch.providers`: versioned, data-driven prompt recognizers for Claude
  Code and Codex CLI. Every pattern records the provider version it was verified
  against, so a future wording change is a table edit and a version bump rather
  than a hunt through code.
- `providers.timeparse`: parses the three reset shapes the CLIs actually emit -
  `resets 8:10pm (Europe/Berlin)`, `resets Mon 12:00am` and `resets in 4h51m`.
  Anything it cannot parse confidently returns `None`, which means "wait for a
  provider signal", never "resume now".
- Recognition of Claude Code's self-healing banner. Since 2.1.234 Claude resumes
  itself, and the supervisor stands down rather than racing it; the case it
  genuinely covers is Claude's own "will not resume on its own".
- Paid, credit-purchase, reset-credit-redemption and model-downgrade prompts are
  recognised specifically so they can be refused.
- Patterns match against both a line-joined and a reflowed rendering of the
  screen, so a provider sentence broken across a terminal soft wrap is still
  recognised.

## [0.6.0] - 2026-09-05

### Added

- `agent_watch.logging_setup`: a key/value event log with size-based rotation
  (10 MB, 5 backups) and owner-only permissions on both the file and its
  directory.
- `fingerprint()`, the only sanctioned way for screen content to influence a log
  line: it returns a 12-character SHA-256 prefix, never the text. `EventLogger`
  deliberately has no free-text method, so "log events, not content" is enforced
  by the API rather than by reviewer discipline.

## [0.5.0] - 2026-09-05

### Added

- `agent_watch.config`: layered configuration with the precedence the vision
  specifies - defaults, then the config file, then the environment, then CLI
  arguments.
- The `KEY=VALUE` config file is *parsed*, never sourced. Sourcing it would hand
  arbitrary code execution to anything that can write it, which is a poor trade
  for a tool whose job is typing into terminals.
- An unknown or malformed setting is an error rather than a silent fallback, so
  a misspelled `RESET_GRACE` cannot quietly become 60 seconds.
- Only `AGENT_WATCH_*` environment variables are honoured, so an unrelated
  `MODE` in the environment cannot reconfigure the supervisor.
- `Policy`, holding the money- and quality-affecting switches. All of them
  default to off, including Codex auto-resume.

## [0.4.0] - 2026-09-05

### Added

- `agent_watch.terminal`: the `TerminalAdapter` protocol, so the supervisor is
  not welded to one emulator and the state machine can be tested end to end.
- `KonsoleAdapter`, driven through Konsole's per-session D-Bus interface
  (`processId`, `foregroundProcessId`, `getAllDisplayedTextList`, `sendText`).
  This is what makes the tool work under Wayland without `xdotool`, `ydotool`,
  screen coordinates or OCR.
- `FakeAdapter`, a scriptable in-memory terminal that records everything sent,
  so idempotency and the danger scenarios can be asserted in milliseconds
  instead of waiting hours for a real quota reset.
- Scrollback is deliberately absent from the adapter interface: only a bounded
  tail of the current screen can be read.

## [0.3.0] - 2026-09-05

### Added

- `agent_watch.classify`: foreground-process classification into CODEX, CLAUDE,
  SHELL, SSH, TMUX, SCREEN, CONTAINER, EDITOR or UNKNOWN.
- A CODEX or CLAUDE verdict needs at least two independent signals before it may
  drive automation, because wrappers change: Codex ships as a Node shim whose
  `comm` is `node` and whose real binary is a child process.
- Blockers (container, SSH, tmux/screen, and multiplexer or SSH *ancestors*) are
  evaluated before agent detection, so Claude running inside tmux is reported as
  unsupported rather than as an automatable agent.
- Contradictory provider evidence fails closed instead of picking a winner.

## [0.2.0] - 2026-09-05

### Added

- `agent_watch.proc`: `/proc` inspection and `ProcessIdentity`, which pairs a
  PID with the kernel start-time counter so a recycled PID can never be
  mistaken for the process the supervisor selected (vision DANGER 1).
- `still_the_same()`, the revalidation primitive used immediately before any
  input is injected.
- `/proc/<pid>/stat` is parsed after the last `)` so a command name containing
  spaces or parentheses cannot shift the field offsets.
- Only environment variable *names* are read, never their values, so tokens in
  the environment are structurally unable to reach a log.

## [0.1.0] - 2026-09-05

### Added

- Project scaffold: `src/`-layout package `agent_watch`, PEP 621 packaging with
  the version read dynamically from `agent_watch.version`, and the
  `agent-watch` console-script entry point.
- Ruff, pytest and coverage configuration.
- A test that fails the build when `CHANGELOG.md` and `__version__` disagree.

## [0.0.1] - 2026-09-05

### Added

- `vision.md`: the product vision for `agent-budget-watch`.
- `PLAN.md`: the implementation plan, including the prompt strings extracted
  from Claude Code 2.1.261 and Codex CLI 0.153.2 and the verified Konsole D-Bus
  capabilities they rely on.
