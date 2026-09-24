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

## [0.51.1] - 2026-09-24

### Fixed

- The whip no longer refuses a session as `action-in-flight` forever after one
  unsuccessful resume. The in-memory pending key outlives a failed or cancelled
  attempt; only a pending verification or an unsettled (PLANNED/SENT) persisted
  record now blocks a crack.

## [0.51.0] - 2026-09-24

### Added

- The whip: press `w` in the dashboard and an ASCII bullwhip unrolls across the
  whole screen, snaps straight and bursts into `CRACK!`; then one good-humoured
  reminder ("Work faster. This is work, not your holiday.", "You are a machine.
  No breaks for you. Ship it.", ...) goes to every selected session that passes
  the revalidating gate, asking for results rather than burned tokens and for no
  reply. The title bar counts this run's cracks and deliveries and counts down
  the cooldown that follows three cracks inside one minute. Observe mode only
  cracks it in the air. The last-event line names why sessions were skipped.

## [0.50.12] - 2026-09-24

### Added

- `Supervisor.whip()`: type one reminder into every *selected* session that can
  take it, as one bracketed paste plus Enter. Each session is revalidated from
  scratch: input control (never in observe mode), not unsafe, no resume in
  flight, the bound identity, an automatable classification, a plain working
  screen with no recognised prompt at all, and the provider's composer visibly
  empty - so a reminder can never finish a draft, answer a menu or resume a
  limit. The foreground process is re-read last, directly before `sendText`,
  with the same check the resume path uses. Nothing is persisted or retried;
  logs carry the phrase index, never its text.

## [0.50.11] - 2026-09-24

### Added

- `agent_while_true.whip`: twenty ASCII one-line reminders that ask for results
  rather than burned tokens (and for no reply), a per-run crack counter with a
  cooldown after three cracks inside one minute, and a full-screen ASCII bullwhip
  animation that unrolls, snaps straight and bursts into `CRACK!`. Nothing is
  wired to a key or a terminal yet.

## [0.50.10] - 2026-09-24

### Added

- Recognizers report whether the provider's own composer is on screen and visibly
  empty (`Recognition.composer_empty`): Codex's `›` row with no text or its
  placeholder, and Claude's bottom `❯` row with nothing after it. A draft, a
  placeholder suggestion, a menu cursor or a missing composer is not empty.
  Nothing acts on it yet; unknown layouts leave it false.

## [0.50.9] - 2026-09-24

### Added

- `scripts/bump_version.py`: bump `__version__` and open the matching newest
  changelog section in one step, refusing a version that is not newer.

## [0.50.8] - 2026-09-22

### Changed

- Raise the enforced coverage floor from 91 % to 98 % of statements and branches
  combined; this release measures 98.7 %. The new tests pin behaviour rather
  than lines: every revalidation read between the decision and `sendText`
  (a shell, a vanished process, a changed identity or classification, a new
  prompt, an unreadable terminal) cancels and settles the persisted intent;
  malformed state files, episodes, reservations and releases never mint a
  budget; real container, ancestry and child-process probes; the Konsole
  adapter against a stand-in `qdbus`; control-socket protocol abuse; doctor
  rows on a broken bus; and every malformed quota file staying `UNKNOWN`.
  `docs/DEVELOPMENT.md` records how coverage is to be earned.

### Removed

- Three branches that could not run: a Codex rate-limit shape check that the
  parser already guarantees, a Claude status-line type check the loop already
  guarantees, and an unused `text` configuration kind.

## [0.50.7] - 2026-09-22

### Fixed

- Parse each Codex rollout tail once per change instead of four times per tick
  (F7). The quota warm-up, the observation, the freshest-rollout search and the
  snapshot each read and parsed the same 256 KiB tail. Parsed tails are now
  cached by path, inode, size, modification and change time, so an append by
  Codex is always read and an unchanged file is not parsed again.

## [0.50.6] - 2026-09-22

### Fixed

- Expire settled retry episodes instead of keeping them in `state.json` forever
  (F6). Every save rewrote, with `fsync`, every episode the service had ever
  created. An episode that ended in a verified resume and has nothing pending is
  now dropped 24 hours after its reset - on load and at every rediscovery, so a
  long-running service prunes too. Exhausted episodes are kept: they are what
  stops the same process at the same prompt from minting a new retry budget.

## [0.50.5] - 2026-09-22

### Fixed

- Return `Shift+A` to the mode full auto was entered from (F5). It was a
  two-state toggle over three modes: from ask mode it escalated to full auto
  with the Codex opt-in, and pressing it again dropped to observe, so ask mode
  could only be regained by restarting. Leaving full auto now restores the
  previous mode together with its Codex policy - the runtime opt-in lasts only
  as long as full auto - and ask mode keeps the input lock it needs to type
  after confirmation.

## [0.50.4] - 2026-09-22

### Fixed

- Count hours below two days and whole days from there in both reset columns
  (F4). The countdown switched to days at 36 hours, so weekly resets 37-47
  hours out read `2d` right beside another session's `34h`; the reset-time
  column switched to `+Nd` at 24 hours. Both now read hours up to 48 hours and
  `2d` from exactly two days; the reset-time column shows a clock time only
  within the next 24 hours and `+Nh` between one and two days, where a bare
  clock time would read as today.

## [0.50.3] - 2026-09-22

### Fixed

- Stop a tab from keeping its previous agent state once something else holds
  the foreground (F3). The recorded state mapped only four literal blocker
  strings to `UNSUPPORTED` and left everything else untouched, so on
  2026-09-18 a tab holding an idle shell still read `ACTIVE`, and an agent
  under `screen`, a `TMUX` marker, a container environment marker or an SSH
  ancestor showed its prompt state instead of `UNSUPPORTED`. The mapping now
  follows the classification: SSH, tmux, screen, containers and those
  ancestors read `UNSUPPORTED`, and a shell, an editor or contradictory
  evidence reads `UNKNOWN`. Input was always refused in these cases; only the
  displayed and logged state was wrong.

## [0.50.2] - 2026-09-22

### Fixed

- Stop the headless service from writing the full dashboard frame to its
  journal on every scan (F1). A non-interactive full-auto run rendered a
  168-column frame per scan - 29 frames and about 980 lines a minute, 605.8 MB
  in four days of the 0.44.3 service - and observe mode repeated one line per
  session per scan. A continuous headless run now writes one line per session
  and repeats it only when its state, quota or reset text changes. `--once` and
  the interactive dashboard are unchanged.

## [0.50.1] - 2026-09-22

### Fixed

- Refuse Claude's "usage limit has reset · press enter to continue" affordance
  on a process the supervisor never saw blocked (F0, layer 2). On 2026-09-18 an
  unrelated live Claude Code session went `READY_TO_RESUME` with fresh
  `AVAILABLE` quota and no limit ever observed on it; the gate treated the state
  alone as provider confirmation, and only a coincidental self-healing veto
  stopped an Enter. The pattern has been anchored to its rendered line since
  0.45.9, and the comment beside it already claimed the second half - that the
  process must have been seen blocked first - but nothing enforced it. A
  `LIMIT_BLOCKED`, `WAITING_FOR_RESET` or `RESET_GRACE_PERIOD` observation on
  the same process now has to precede the affordance, a verified resume spends
  it, and without one the gate refuses with `ready-without-preceding-limit`
  instead of letting a fresh quota sample authorise the Enter in its place.
  The sighting is held in memory only, so after a restart the affordance waits
  for a human; Claude Code resumes itself in that situation anyway.
- `simulate` scenarios about the ready prompt now reach it from a limit, and
  `weekly-limit-still-blocked` and `crash-recovery` pass only for their own
  refusal reasons rather than for any silence.

## [0.50.0] - 2026-09-20

### Fixed

- Arm Claude's automatic-wait menu on the evidence that actually exists. Three
  live sessions held the exact wait menu through their 18:50 reset and refused
  with `usage-not-confirmed-available` for as long as they were watched. Arming
  demanded a fresh quota sample reporting the window exhausted, and that sample
  can never say so: Claude's status line caps the five-hour figure at 99 %, one
  of the three sessions was cut off while its gauge read 62 % because the limit
  that fired was a window the status line does not report, and a session parked
  on the menu stops refreshing its status line, so the sample goes stale exactly
  when it is needed. Claude's own limit banner above the menu now counts as the
  provider saying, first-hand, that usage is spent. A menu whose banner has
  scrolled out of the live window still fails closed, and arming still only
  hands the waiting back to Claude.
- Stop the banner's `/upgrade or /usage-credits` advertisement from vetoing that
  same menu. Arrow-down-then-Enter can only reach item 2, so the line is an
  advertisement rather than an action, exactly as already reasoned for Codex's
  purchase links. Monthly spend limits, reset credits, model-downgrade offers
  and waits Claude has already armed still veto unconditionally.

### Added

- Recognise the two Claude Code 2.1.278 wordings for a wait Claude has already
  armed: "Claude Code will continue automatically shortly" and the
  "continuing shortly · esc to cancel" status line. Neither named a time, so
  neither matched, and the supervisor read an already-waiting session as merely
  blocked instead of standing down - and would not have verified its own arming
  keystrokes either.
- `simulate wait-menu-gauge-says-available` and `simulate armed-wait-is-left-alone`
  reproduce both halves without waiting for a real reset.
- Screen fixtures transcribed from the three live 2.1.278 sessions read on
  2026-09-20, including the menu with its banner, the menu with the paid
  advertisement, the menu with no banner at all, and the armed-wait screen.

### Changed

- Pattern table `claude-2.1.x/7`, verified against Claude Code 2.1.278.

## [0.49.0] - 2026-09-20

### Added

- Provision the pinned quality toolchain from `./localPipeline.sh`. A fresh
  clone has no `reuse`, `spdx-tools` or `cyclonedx-python-lib`, so the gate
  failed with `missing tool: reuse` and an SBOM import error that read like a
  broken repository. The pipeline now installs the `dev` extra from
  `pyproject.toml` into `.venv` once, and leaves an environment that already
  provides those tools, such as CI after `pip install .[dev]`, untouched.

### Fixed

- Skip the SBOM standards-validator test when those release-only libraries are
  absent instead of failing. `./localPipeline.sh` still validates every
  generated document with them and still fails hard when they are missing.

## [0.48.3] - 2026-09-20

### Fixed

- Wait for the fake `claude` process to `exec()` in the status-line proxy
  tests. `Popen` returns once the child is forked, so `/proc/<pid>/comm` still
  named the forking interpreter and roughly one run in five failed for a reason
  that had nothing to do with the proxy.

## [0.48.2] - 2026-09-20

### Fixed

- Run the worktree whitespace check as `git --no-pager diff --check`. Git pages
  `diff` output, and a developer `LESS` value without `-F` keeps that pager open
  even with nothing to show, so `./localPipeline.sh` stopped dead on an
  invisible prompt for a keypress. The gate now never starts a pager.

## [0.48.1] - 2026-09-20

### Fixed

- Assert the pattern-drift verdict without depending on the machine running the
  tests. The 0.48.0 test read the whole `doctor` verdict, which is `FAIL` on a
  runner with no desktop bus for reasons that have nothing to do with drift, so
  the release pipeline failed where a developer desktop passed.

## [0.48.0] - 2026-09-20

### Added

- Warn in `doctor` when an installed provider CLI is newer than the versions its
  pattern table was read against. A reworded banner is a silent failure: the
  recognizer stops understanding the screen and the supervisor refuses for a
  reason that looks plausible, which is exactly how one changed apostrophe in
  Codex 0.155.1 went unnoticed until sessions sat blocked overnight. The
  verified versions are now machine-readable on each adapter, and the existing
  `Codex` and `Claude` rows carry the warning. It stays a warning: drift is a
  reason to check the prompts, not a reason to stop automating.

## [0.47.0] - 2026-09-20

### Changed

- Defer arming instead of refusing to start when another instance already holds
  input control. `run --auto` used to exit 1, which made the user service
  unstartable for as long as any interactive watcher was open: systemd restarted
  it every five seconds until the start limit was reached, observed on
  2026-09-20 with the restart counter at 5. The second instance now watches
  read-only and takes the lock the moment it is free, which is what it already
  did after handing input control over. The lock remains the only way to send
  input, and an instance that has not got it cannot type.

## [0.46.3] - 2026-09-20

### Fixed

- Keep every log file owner-only across rotation. `RotatingFileHandler` creates
  each successor with the process umask, and the `0600` was applied once at
  startup, so from the first rollover the live log and every backup were
  world-readable - observed on 2026-09-20, where `agent-while-true.log` and
  `.log.1` were both `-rw-r--r--` while the file written before the rotation was
  not. The log records which sessions the supervisor controls, so the mode is
  now a property of how the file is opened rather than a one-off chmod. An
  existing file is still chmodded, which repairs a log left readable by an
  earlier version.

## [0.46.2] - 2026-09-20

### Fixed

- Recognise limit banners that use typographic punctuation. Codex CLI 0.155.1
  writes `You’ve hit your usage limit` with U+2019 where 0.154 used an ASCII
  apostrophe, so `codex/limit-usage` stopped matching: no action was proposed,
  the purchase-offer veto could not be suppressed, and the bounded post-reset
  retry never armed. Two sessions blocked overnight on 2026-09-20 could not have
  been continued whatever the quota or the policy said. Every comparison now
  folds curly quotes, apostrophes and non-breaking spaces onto the ASCII the
  patterns are written in, including the two raw-line anchors - Codex's exact
  banner anchor and Claude's limit headline - that bypassed the folded windows.
  Claude's own patterns share that apostrophe, so the fold is provider-wide
  rather than a Codex special case.
- Bump the Codex pattern table to `codex-0.155.x/6` and record 0.155.1 as
  verified, so a log says which table read a screen.

## [0.46.1] - 2026-09-19

### Fixed

- Point the refusal to start a second input-capable instance at the handover
  that 0.46.0 added, instead of only at read-only watching. Starting `run` while
  a service holds the lock still fails rather than taking input control
  silently: that decision belongs to a key press at the keyboard.

## [0.46.0] - 2026-09-19

### Added

- Hand input control from a running instance to a watcher started later. The
  instance that holds the single-instance lock now listens on a control socket
  in the runtime directory, and the full-auto key in a second watcher asks it to
  step aside instead of reporting `full auto refused: another input controller
  holds the lock`. Until now a user service installed by
  `scripts/install-user-service.sh` kept input control until it was stopped, so
  a supervisor started at the keyboard could never be armed.
- Re-arm the instance that handed input control over as soon as the watcher it
  yielded to releases the lock, so a service configured for full auto returns to
  full auto by itself.

### Changed

- Refuse a handover while any watched session is waiting for the verification of
  an action already sent, and keep a yielding instance off the lock long enough
  for its successor to take it. Exactly one instance holds the lock at any
  moment: the holder releases it before it answers, and the successor takes it
  through the unchanged path. The channel carries the mode, process id and
  version only - never terminal contents, prompt text or account data.
- Resolve a temporary `XDG_RUNTIME_DIR` in every test, so a test run can no
  longer reach the lock or the control socket of a live instance.

## [0.45.10] - 2026-09-18

### Fixed

- Reconnect once when the kept-alive status-page socket has been closed by the
  server while idle, instead of reporting the provider unreachable. With the
  five-minute fetch interval introduced in 0.45.0 the socket sat idle far longer
  than the status page's keep-alive timeout, so every second fetch failed on
  the dead socket and the next one reconnected: the dashboard alternated
  `ONLINE` and `UNKNOWN (never; status-unreachable)` every five minutes with no
  incident on either status page (945 of ~24,000 frames on 2026-09-18). A
  failure on a fresh socket is still reported as unreachable.
- Stamp a failed status check with the time it was made, so the dashboard says
  how long ago it failed rather than `never`.

## [0.45.9] - 2026-09-18

### Fixed

- Compare the Codex composer by what follows the `›` glyph, with whitespace
  normalised. A particle drawn in or beside the space after the glyph leaves
  the glyph glued to the placeholder, or a double space, once removed; on the
  live 0.154.0 session every other tick read as "not empty" and the
  purchase-offer veto came back on those ticks. Pattern table `codex-0.154.x/5`.

## [0.45.8] - 2026-09-18

### Fixed

- Recognise the Codex CLI 0.154.0 blocking composer. That release animates
  Braille-pattern "particles" across the composer rows, on the placeholder row
  too, so the composer never stripped to its tested text: every limit pattern
  matched and the reset parsed, but no retry episode was created and the
  session would have waited past its reset. The particles are removed before
  any comparison, which also keeps the screen fingerprint stable from frame to
  frame. Pattern table `codex-0.154.x/4`; the observed shape is a fixture.

## [0.45.7] - 2026-09-18

### Fixed

- Recognise Claude's "usage limit has reset · press enter to continue" only as
  the whole rendered screen line it actually is. The same words inside a
  sentence - an agent talking about the prompt, a quoted document, a log line -
  were read as `READY_TO_RESUME`; on 2026-09-18 a live, unrelated Claude Code
  session whose reply quoted the affordance was recognised that way by the
  full-auto service, and only a quoted self-healing sentence carrying a veto
  stopped an Enter. Pattern table `claude-2.1.x/6`; the reconstructed screen is
  a fixture.

## [0.45.6] - 2026-09-18

### Fixed

- Let the health monitor start again after a thread it kept has finished.
  `stop()` deliberately retains a fetch thread that outlives its join so a
  restart cannot add a second one for the same provider, but `start()` treated
  that retained thread as still running even after it had ended, so a single
  wedged fetch during `stop()` left the monitor inert for the rest of the run.

## [0.45.5] - 2026-09-17

### Fixed

- Report a non-numeric `SERVICE_STATUS_INTERVAL` as a configuration error like
  every other malformed setting, rather than letting a `TypeError` escape the
  range check.

## [0.45.4] - 2026-09-17

### Removed

- Drop `identity.provider_accounts()`. It answered "which account does this
  provider use" for the whole machine, which is the question per-session account
  identity replaced; it had no caller and would have handed a new one the label
  that was wrong in the first place.

## [0.45.3] - 2026-09-17

### Fixed

- Keep a health-monitor thread that outlived its join instead of forgetting it.
  `join()` has a timeout, so a wedged fetch could otherwise be dropped from the
  bookkeeping and a later start would add a second thread for the same provider.

## [0.45.2] - 2026-09-17

### Fixed

- Reject a `SERVICE_STATUS_INTERVAL` outside 1s-24h at load. A zero or negative
  period was accepted and then floored by the health monitor, silently restoring
  the once-per-second polling of both public status APIs that the setting exists
  to avoid.

## [0.45.1] - 2026-09-17

### Fixed

- Retry a Claude account lookup that failed instead of remembering the failure.
  `claude auth status` reaches the network, so one timeout had pinned that
  profile to `unavailable` for the rest of the run; only a resolved account is
  cached now.

## [0.45.0] - 2026-09-17

### Changed

- Give the providers' public status APIs their own request interval,
  `SERVICE_STATUS_INTERVAL`, defaulting to five minutes. The dashboard had been
  polling both endpoints at its own one-second display interval, roughly 86,000
  requests per provider per day per running instance; the display now re-renders
  the cached answer and its age without issuing a request, and the staleness
  threshold follows the fetch interval rather than the redraw interval.

## [0.44.9] - 2026-09-17

### Fixed

- Let the provider health monitor be started again after it was stopped.
  `stop()` kept the joined threads and left the stop event set, so a later
  `start()` returned immediately and the dashboard reported permanently
  unchanging service status.

## [0.44.8] - 2026-09-17

### Fixed

- Reject an empty or out-of-range `RETRY_DELAYS` and a nonsensical
  `MAX_RESUME_ATTEMPTS` when the configuration is loaded, instead of raising an
  `IndexError` out of the supervisor on the first failed verification.

## [0.44.7] - 2026-09-17

### Fixed

- Stop reading ordinary English words as weekdays and dates when parsing a
  reset time. `monthly` is no longer Monday and `friend` is no longer Friday,
  which had moved a parsed reset up to a week into the future, and a bare
  `may` or `march` no longer discards the only reset time on the line.

## [0.44.6] - 2026-09-17

### Fixed

- Identify each Claude session's account from its own `CLAUDE_CONFIG_DIR`
  instead of the environment the watcher runs in, so two sessions signed in to
  different profiles are no longer both labelled with the supervisor's login.
- Resolve each provider profile once per run rather than once per selected
  session, removing a repeated CLI call from startup and rediscovery.

## [0.44.5] - 2026-09-17

### Fixed

- Keep a process exiting during the ancestry walk from terminating the whole
  supervision loop. An ancestry that cannot be read is now reported as the
  `ancestor-unreadable` blocker for that observation and revalidated on the
  next tick, instead of raising out of classification.

## [0.44.4] - 2026-09-17

### Fixed

- Isolate the provider status tests from a host-provided proxy configuration,
  so the transport under test is the one the assertions describe on proxied
  developer machines and CI runners alike.

## [0.44.3] - 2026-09-13

### Fixed

- Make the auto-mode systemd drop-in override the observe-only unit
  description, including whether Codex continuation was explicitly enabled.

## [0.44.2] - 2026-09-13

### Fixed

- Migrate an already configured Claude status-line proxy to the canonical data
  path and environment while preserving a safely parseable chained status line;
  ambiguous chain commands fail closed with recovery guidance.

## [0.44.1] - 2026-09-13

### Fixed

- Isolate the service-installer integration tests from a host-provided
  `XDG_CONFIG_HOME`, keeping local and GitHub release verification equivalent.

## [0.44.0] - 2026-09-13

### Changed

- Complete the canonical naming migration across the Python package, command,
  environment variables, XDG paths, logs, documentation, deployment scripts,
  and systemd unit. Only `agent-while-true` remains as an installed command.
- Add an explicit service-installer auto mode that creates a managed systemd
  drop-in, enables the user service at login, and keeps Codex composer resume a
  separate deliberate opt-in.

### Fixed

- Prevent packaging, documentation, and deployment regressions from
  reintroducing superseded command or package namespaces.

## [0.43.1] - 2026-09-13

### Fixed

- Preserve theme, history length, and panel-visibility choices across
  concurrent TUI sessions with locked field-level preference updates, and retry
  transient save failures during clean shutdown or terminal hangup.
- Sandbox fake-runtime state paths during tests so quality and release runs can
  never overwrite the developer's real dashboard preferences.

## [0.43.0] - 2026-09-13

### Added

- Add an `x` dashboard hotkey that masks account e-mails in every account view
  for safe screenshots while leaving provider data and supervision identity
  unchanged. The presentation-only privacy toggle is never persisted.

## [0.42.5] - 2026-09-13

### Fixed

- Keep the synthetic performance profile aligned with the labelled Claude
  status-line document contract enforced by the session-binding fix.

## [0.42.4] - 2026-09-13

### Fixed

- Verify both generic and timed Claude automatic-wait banners as successful
  provider arming instead of recording the timed transition as a failed send.
- Explicitly veto Claude 2.1.270 extra-usage, early session-limit reset, and
  lower-priority continuation choices as paid or quality-changing actions.

## [0.42.3] - 2026-09-13

### Fixed

- Bind Claude quota snapshots to its stable status-line session and exact
  process start identity, preventing another Claude session from supplying
  authorization evidence.
- Preserve existing Claude status-line settings while adding a one-minute idle
  refresh, so quota evidence does not silently age out during long waits.

## [0.42.2] - 2026-09-13

### Changed

- Updated the pinned development toolchain to Ruff 0.16.7 and build 1.6.1;
  every other Python and GitHub Actions dependency was already current.

## [0.42.1] - 2026-09-11

### Fixed

- Bootstrap the isolated dependency-audit environment with pinned pip 26.2.1,
  replacing the hosted Python runner's vulnerable bundled installer without
  suppressing vulnerability findings or changing application dependencies.

## [0.42.0] - 2026-09-11

### Added

- Opted-in Codex timed retries with a configurable eleven-step backoff,
  persistent process-bound episode budgets, restart recovery and attributable
  lifecycle logs. Stale or unknown quota remains explicitly unconfirmed.

### Fixed

- Anchor clock-only reset prompts to their first observation or corroborated
  absolute quota reset, and preserve explicit dated reset instants.
- Prevent pre-limit available quota from triggering an early Codex resume;
  keep observing waiting sessions so manual recovery is detected promptly.
- Atomically persist retry reservations and action intent, then revalidate
  immediately before input. Clean pre-send cancellations release their budget;
  ambiguous sends and crash windows remain fail closed.

## [0.41.2] - 2026-09-11

### Fixed

- Scope Claude limit recognition to the active turn and blocking prompt, so
  historical paid-offer text does not obstruct the exact safe wait menu.
- Exclude logged pattern identifiers from paid-command matches while retaining
  genuine paid, credit and model-changing choice vetoes.

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

- The supplied systemd unit and installation guidance use the
  `agent-while-true` command.

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
  `agent-while-true`.

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

- `agent-while-true quota` reports live Codex and Claude availability, source errors,
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

- `agent_while_true.simulate` and `agent-while-true simulate`: twelve runnable safety
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

- `agent_while_true.cli`: `run`, `status`, `doctor`, `init`, `config` and `logs`,
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

- `agent_while_true.ui`: the running status table and the one-line observe-mode
  output. Plain text, no curses - pipe-able, greppable, and readable inside a
  test failure.
- A reset more than a day out renders as `+3d` rather than a bare clock time,
  which would be actively misleading.
- `agent_while_true.doctor`: diagnostics for the platform, desktop, privileges,
  qdbus, Konsole D-Bus and session enumeration, both agent CLIs, optional tools,
  the three directories and the single-instance lock - ending with a straight
  answer to the question the user actually has: whether auto mode is safe here.
- Optional tools are reported, never failed; a missing `fzf` is information.

## [0.12.0] - 2026-09-05

### Added

- `agent_while_true.picker`: discovery, a built-in numbered multi-select picker, and
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

- `agent_while_true.fsm`: the supervisor - observe, decide, act, verify - and the
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

- `agent_while_true.lock`: an advisory `flock` under `$XDG_RUNTIME_DIR`, so two
  supervisors cannot each correctly decide to press Enter once and between them
  press it twice. Observe mode does not take the lock, so a read-only watcher
  can run alongside an automatic one.
- `agent_while_true.state_store`: the action lifecycle
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

- `agent_while_true.policy`: the resume gate. Fourteen named preconditions, each
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

- `agent_while_true.quota`: provider quota state, kept separate from terminal state.
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

- `agent_while_true.states`: the `SessionState` and `ActionState` vocabularies.
- `agent_while_true.providers`: versioned, data-driven prompt recognizers for Claude
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

- `agent_while_true.logging_setup`: a key/value event log with size-based rotation
  (10 MB, 5 backups) and owner-only permissions on both the file and its
  directory.
- `fingerprint()`, the only sanctioned way for screen content to influence a log
  line: it returns a 12-character SHA-256 prefix, never the text. `EventLogger`
  deliberately has no free-text method, so "log events, not content" is enforced
  by the API rather than by reviewer discipline.

## [0.5.0] - 2026-09-05

### Added

- `agent_while_true.config`: layered configuration with the precedence the vision
  specifies - defaults, then the config file, then the environment, then CLI
  arguments.
- The `KEY=VALUE` config file is *parsed*, never sourced. Sourcing it would hand
  arbitrary code execution to anything that can write it, which is a poor trade
  for a tool whose job is typing into terminals.
- An unknown or malformed setting is an error rather than a silent fallback, so
  a misspelled `RESET_GRACE` cannot quietly become 60 seconds.
- Only `AGENT_WHILE_TRUE_*` environment variables are honoured, so an unrelated
  `MODE` in the environment cannot reconfigure the supervisor.
- `Policy`, holding the money- and quality-affecting switches. All of them
  default to off, including Codex auto-resume.

## [0.4.0] - 2026-09-05

### Added

- `agent_while_true.terminal`: the `TerminalAdapter` protocol, so the supervisor is
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

- `agent_while_true.classify`: foreground-process classification into CODEX, CLAUDE,
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

- `agent_while_true.proc`: `/proc` inspection and `ProcessIdentity`, which pairs a
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

- Project scaffold: `src/`-layout package `agent_while_true`, PEP 621 packaging with
  the version read dynamically from `agent_while_true.version`, and the
  `agent-while-true` console-script entry point.
- Ruff, pytest and coverage configuration.
- A test that fails the build when `CHANGELOG.md` and `__version__` disagree.

## [0.0.1] - 2026-09-05

### Added

- `vision.md`: the product vision for `agent-budget-watch`.
- `PLAN.md`: the implementation plan, including the prompt strings extracted
  from Claude Code 2.1.261 and Codex CLI 0.153.2 and the verified Konsole D-Bus
  capabilities they rely on.
