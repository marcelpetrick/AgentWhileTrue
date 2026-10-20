<!--
SPDX-FileCopyrightText: 2026 Marcel Petrick

SPDX-License-Identifier: GPL-3.0-or-later
-->

# Agent While True contributor instructions

These instructions apply to the entire repository.

## Purpose and priorities

Build a conservative supervisor for Codex CLI and Claude Code sessions in KDE
Konsole. Correct refusal is more important than eager automation. Keep provider
quota state separate from terminal prompt state, revalidate immediately before
input, and fail closed on ambiguity.

Read `docs/vision.md`, `docs/PLAN.md`, `docs/ARCHITECTURE.md`, and `docs/USAGE.md`
before changing runtime behavior; `README.md` is the short entry page.
The real prompt captures in `media/` are evidence; transcribe them into fixtures
when recognizer behavior changes.

## Scope

- GitHub Actions live in `.github/workflows/` and run from the repository root.
- Keep the package, tests, scripts, documentation, and workflows independently
  usable as a standalone repository.
- Do not change terminal, provider, account, subscription, or paid settings as
  a side effect of development.

## Safety invariants

- Observe mode never sends input.
- Unknown, missing, stale, or malformed quota data never means available.
- A reset timestamp never means quota is available. The sole timed-retry
  exception is explicitly opted-in Codex continuation of its exact tested limit
  composer after an anchored reset, with a persistent bounded retry schedule,
  no fresh contradictory quota and immediate identity/prompt/policy revalidation.
  Claude and every other action still require provider confirmation.
  Codex recovery needs two working observations at least three seconds apart;
  an identical returning limit reuses its retained reset and spent attempts,
  including after restart. A genuinely later date needs matching fresh absolute
  provider evidence before it can replace a completed anchor.
- Bind a selection to Konsole service/session plus PID, process start time, and
  TTY; never transfer an interactive selection to a replacement process.
- Re-read session identity, process class, visible prompt, and policy directly
  before `sendText`.
- Never automate upgrades, purchases, paid credits, reset credits, or any model
  change (including upgrades, downgrades and fallbacks). Paid choices belong to
  the human operator; no configuration flag may authorize the supervisor to
  make them. A tested model-choice dialog may only retain the existing model
  through its exact safe decline/stay choice, never by guessing an answer or
  typing free text into an arbitrary question. Without an observed, regression-
  tested stay choice, report `stay with same model` and leave the dialog manual.
- Quota exhaustion means wait for the relevant provider-confirmed budget
  renewal, not switch model or buy capacity. Respect every exhausted window
  (including weekly/model-specific limits), provider reset and grace period;
  resume only a still-bound tested limit continuation after fresh availability,
  or the existing explicitly opted-in bounded Codex exception. An already-armed
  Claude wait is left to Claude. Never infer task completion or renewed budget
  from the reset clock alone.
- Select Claude's automatic-wait item only for the exact tested menu with the
  cursor visibly on item 1, safe item 2, `allow_claude_auto_wait`, and evidence
  that usage is spent: either fresh exhausted quota or Claude's own limit banner
  on the same screen. A usage gauge alone cannot carry that evidence - the
  status line caps at 99 %, misses the window that fires, and goes stale while
  the session is parked - so the banner outranks it. Arming only hands the
  waiting back to Claude; it never claims usage returned. Every variation,
  including a menu with no banner, fails closed.
- Codex resume types into its composer and therefore remains opt-in.
- The dashboard whip (`w`) is the only operator-initiated free-text input. It
  never types in observe mode, while paused or without input control; only
  into a selected, revalidated session with a plain working screen, a visibly
  empty provider composer and quota that is not exhausted; it is never
  persisted or retried, and it is limited to five cracks per rolling minute.
- Claude Code and Codex CLI permission prompts are never resume prompts. Only the operator's
  dashboard auto-yes switch (`y`) answers one: off at every start, never
  persisted, only in full-auto - never in ask or observe mode, while paused or
  without input control;
  for Claude, only an exact tested permission menu - a whole-row "Do you want to ...?",
  the cursor on `1. Yes`, zero to two consecutive `Yes, and ...` choices, and
  a final numbered `No` - alone on the screen and unchanged since the scan,
  once per appearance, by Enter on item 1. The identical box still on screen
  3 seconds after its answer counts as an Enter that did not land and gets
  exactly one more Enter, through the full revalidation; if it stays after
  that too it is reported once and left to the operator. If a full-window
  preview scrolls away the box's top rule, require the dashed separator plus
  an exact observed permission explanation and fingerprint the visible preview
  too. Never select a "Yes, and ..." item: those change provider settings or
  session modes. For Codex, require one of the complete 0.162.1 command,
  patch, terminal-input, one-time-network or turn-permission menus, its exact
  title and footer, the cursor on the exact one-turn item 1, every consecutive
  persistent middle choice and its final denial. Codex gets no resend: an
  unchanged overlay after 3 seconds is reported and left to the operator.
  Never answer MCP elicitation,
  user-verification, arbitrary questions or an unknown/reworded menu.
- Never log terminal contents, environment values, credentials, or prompt text.
- Detached Codex quota may use only the bounded read-only existing-daemon proxy:
  initialize/initialized and account/rateLimits/read, with explicit OAuth and
  no login, turn, thread, model, payment or reset operation. Revalidate the
  selected process start time, profile and private account identity before and
  after each read (including cache hits); require a matching response account
  and explicit ordinary-usage allowance. Never guess a shared daemon rollout.
- Claude's exact trailing background-agent panel may be excluded from turn
  scoping only to recover a recognized already-armed waiting footer with no
  action. Never expose a historical actionable menu or reset prompt this way.
  Keep full-screen composer/permission validation and paid-action vetoes.
- Preserve the persisted action lifecycle and single-instance lock.
- Treat SSH, containers, tmux/screen, conflicting classification signals, and
  unsupported prompts as non-automatable.

Live Konsole sessions may be used for read-only inspection. Do not send input to
a real session unless the user has explicitly authorized that validation and
the normal policy/revalidation gate allows the exact action. Never use a paid or
quality-changing choice as a test.

## Working style

- Make one logical change per commit.
- Every feature or fix commit bumps `src/agent_while_true/version.py` and adds the
  matching newest section to `CHANGELOG.md`.
- Every other commit also bumps the patch version and adds a matching newest
  `CHANGELOG.md` section. Substantial product features bump the minor version;
  fixes, tests, documentation, CI, build and maintenance changes bump the patch
  version.
- Use commit subjects in the existing style, for example
  `feat(AgentWhileTrue): ...` or `fix(AgentWhileTrue): ...`.
- Do not amend or rewrite commits that are not yours.
- Preserve uncommitted user work and inspect the worktree before staging.
- Keep runtime dependencies empty unless there is a compelling documented
  reason; CPython 3.14.x standard library is the sole baseline. Do not add
  compatibility code or CI jobs for older or unreviewed future Python minors.
- Keep shell limited to deployment/integration jobs and ShellCheck-clean.
- Prefer deterministic fake-terminal tests over waiting for a real quota reset.
- When a bug is found from a live prompt, add a regression fixture before the
  fix.

## Working with the maintainer

The maintainer's standing requests, collected from their sessions:

- Work fast and finish. Make a short plan, present it, then execute it end to
  end without stopping for confirmation; "get it done" means every step,
  including the fixes a review turns up.
- Ask only when a decision truly belongs to the maintainer, and ask it once and
  briefly. Otherwise pick the sensible option, say which, and continue.
- Make atomic commits: one logical change each, every one passing the required
  verification below. Committing is expected; pushing and tagging wait for an
  explicit request unless the maintainer has requested continuous pushes for
  the current task.
- Keep everything testable and tested: unit tests for the gate, dashboard-loop
  tests for keys, a `simulate` scenario for each safety behaviour, and a real
  pseudo-terminal end-to-end test (`tests/pty_dashboard.py`) for anything the
  dashboard shows.
- After a feature, self-review it with `/reviewBranch` (base: the last commit
  before the feature when working on `master`) and fix every finding.
- Use subagents for independent parts of the work where possible, and keep the
  documentation current: a behaviour change updates every document that
  describes it.
- A bug seen live, often reported as a screenshot, is debugged from the live
  session read-only: read the screen through the Konsole adapter, find the
  root cause, add a fixture transcribed from that screen, then fix.
- Finish by presenting a running version: the full pipeline result, the
  commits, and whether the running dashboard must be restarted to pick up the
  change (a running `agent-while-true` keeps the code it started with).
- Dashboard automation switches are separate toggles with their own hotkeys,
  always visible with their state in the header: `A` auto-resume on limit and
  `y` auto-yes on permission prompts.
- Work directly on the repository's current default branch (`master`) for
  maintainer-directed end-to-end work. When the maintainer explicitly requests
  continuous pushes, push every atomic green commit to `origin/master`; never
  force-push or rewrite published history.
- Document every reusable script: its purpose, normal invocation, inputs,
  outputs and safety limitations.
- Support only the most recent stable CPython minor (currently 3.14). Remove
  code, configuration and documentation written for older minors instead of
  keeping it; archived plans under `docs/history/` may keep past results.
- "Update the dependencies" covers every exact pin: the dev extra and build
  backend in `pyproject.toml`, the pinned GitHub Actions and the container base
  image digest, each moved to its latest stable release through the pipeline.
- A new Claude Code or Codex release that changes a screen (a new panel, footer
  or status row) is the usual cause when a working feature stops working. Read
  the live screen first, transcribe it into a fixture, and fail closed on any
  row that was not observed.
- Support only the latest Claude Code and Codex CLI releases; the maintainer
  updates both as soon as a new one ships, so older binaries do not matter.
  Verify each new release from its live screen and its binary's strings,
  record only that version in `VERIFIED_VERSIONS`, and keep no version history
  in code comments or documentation. Never drop a refusal or veto pattern just
  because its literal is missing from the binary: Codex and Claude assemble
  some screen text at runtime.
- "Deploy a new version" or "make a public release" means the whole release
  procedure below: push, annotated tag, green release workflow, then
  reinstall the tagged version with pipx and restart the user service
  `agent-while-true.service` so the background watcher runs the new code.

## Live monitoring and handoff

Monitoring means actively inspecting the running supervisor and provider sessions,
not assuming an installed release is the process controlling input. Keep the
existing operator's selections, input lock and automation switches unchanged.

1. Establish the scope and deadline from the maintainer's request, including the
   timezone. For a renewed request, start a new observation period; do not reuse
   an expired overnight deadline. Continue until that deadline, or explicitly
   report when observation ends. Never imply monitoring continues after it stops.
2. Inspect the worktree, installed `agent-while-true --version`, user-service
   state, and the input controller's read-only `OP_STATUS` response. Record
   controller PID, mode and version separately from the installed/service
   version. An old dashboard retains its loaded code after a pipx reinstall.
3. Run `doctor`, `status`, `quota`, `logs -n 50` and `summary`. Discover current
   Konsole sessions through the adapter and process inspector, including default
   and company profiles (`claude`, `claude-dmo`, `codex`, `codex-dmo`) where
   present. Check the requested hot repositories, normally `~/repos/hr-doccontrol`
   and `~/repos/mpt`, but do not mistake an exited agent or idle shell for a
   blocked task. Bind every observation to service/session/PID/start time/TTY.
4. Repeatedly read visible screens through the Konsole adapter and recognize
   them with the code being validated; compare fresh process-bound quota and
   structured lifecycle events. Inspect persistent approval/unknown prompts,
   possible unanswered questions, failed or exhausted retries, and quota limits
   misclassified as active. Attention heuristics may flag a screen for inspection;
   they must never become permission or resume rules by themselves.
5. Prefer a bounded read-only observer alongside the existing controller. The
   supported CLI alternative is `agent-while-true run --observe --all`; it is a
   complete second watcher, not an attach-only viewer, and contributes duplicate
   observations to shared logs and summaries. Never press takeover, auto, auto-yes
   or whip keys just to inspect. Keep individual waits at most 60 seconds and
   check for new user instructions and alerts between waits.
6. Store only metadata: timestamps, identity/profile identifiers, state, quota
   availability, pattern/veto IDs and structured action outcomes. Use an
   owner-only directory for temporary reports. Do not persist raw screens,
   transcripts, draft text, account e-mails, credentials or environment values.
   Inspect screens in memory; transcribe only a minimal privacy-redacted prompt
   fixture when a reproducible bug warrants a regression test.
7. On a new finding, capture the redacted fixture before changing recognition,
   demonstrate a failing deterministic test, then fix the narrow responsible
   layer. Add lifecycle, simulation and PTY coverage where affected, update the
   behavior documents and plan, independently review, and run the complete gate.
   New wording alone does not justify accepting arbitrary questions or relaxing
   paid-choice, quota, identity or revalidation safeguards.
8. Verify recovery from provider evidence, not a reset clock or an `ACTIVE`
   label alone. Distinguish `armed-provider-wait`, actual post-reset activity and
   completed task work. A cleared footer and fresh quota can support recovery;
   neither proves uninterrupted progress or that every possible prompt is covered.
9. End with the observation interval, findings, regression/release results,
   remaining manual blockers and exact running versions. Do not silently restart
   an operator dashboard: auto-yes intentionally resets to off. For a requested
   deployment, restart the service after installation and tell the operator when
   the dashboard needs restarting and its intended `A`/`y` switches re-enabling.

Temporary monitoring scripts are not a supported installed interface. If one is
kept as a reusable repository script, document its invocation, deadline, inputs,
metadata output, privacy boundary and read-only guarantees, and test it normally.

## Required verification

Before every commit and push, run the canonical pipeline:

```bash
./localPipeline.sh --noRun
```

It must include licensing, linting, formatting, shell checks, dedicated static
type checking, unit/integration/pseudo-terminal end-to-end tests, at least 95%
combined coverage (this repository enforces 98%), all safety simulations,
source and wheel builds, isolated installation smoke tests, SBOM validation and,
once Docker support exists, a container build and smoke test. GitHub Actions
must call the same pipeline instead of maintaining a weaker duplicate.

The fast constituent checks remain useful while developing:

```bash
ruff check .
ruff format --check .
shellcheck --severity=style *.sh scripts/*.sh
python3 -m pytest -q
git --no-pager diff --check
```

Before tagging, and as final release diagnostics:

```bash
./localPipeline.sh
PYTHONPATH=src python3 -m agent_while_true.cli simulate --all
PYTHONPATH=src python3 -m agent_while_true.cli doctor
PYTHONPATH=src python3 -m agent_while_true.cli status
PYTHONPATH=src python3 -m agent_while_true.cli quota
```

Run the opt-in live test where KDE Konsole is available:

```bash
AGENT_WHILE_TRUE_LIVE_KONSOLE=1 python3 -m pytest -q -m konsole
```

Build a wheel and install it into an isolated environment before a release.
Confirm that installed `agent-while-true --version`, `doctor`, `quota`, and
`simulate --all` work without `PYTHONPATH`.

## Container boundary

- A published container is a packaging and deterministic-test environment, not
  authorization to control host Konsole. Do not mount host D-Bus, host `/proc`,
  provider credentials or terminal sockets merely to make automation appear
  functional.
- Run the image as a non-root user. Its smoke test must prove at least
  `--version`, `--help` and `simulate --all`; `doctor` must truthfully report
  that host terminal automation is unavailable.
- Publish verified images to GHCR only through the documented GitHub workflow,
  with immutable version tags.

## Documentation and completion

- README delivery changes keep badges, local installation, pipeline, Docker,
  GHCR, testing and usage instructions current and include a current,
  privacy-redacted real Konsole screenshot.
- Before declaring a feature complete, run `/reviewBranch` against the commit
  immediately preceding the feature, fix every finding, then run `/githubAbout`.
- Final delivery requires the complete local pipeline, green GitHub Actions, a
  working container smoke test, all intended commits pushed and a clean
  worktree.

## Release procedure

1. Ensure the worktree contains only intended changes.
2. Run `./localPipeline.sh`; it includes the package smoke tests.
3. Point the `pipx install` command in `README.md` at the new tag in the same
   commit that is tagged; intermediate versioned commits leave it alone.
4. Push the atomic commits to `origin/master` only when requested; when the
   current task requests continuous pushes, push each green commit.
5. Create an annotated `agentwhiletrue-vX.Y.Z` tag only for a fully verified
   version and push that tag to trigger the release workflow.
6. Verify the GitHub Actions quality, security and release results.

Do not tag merely because a version was bumped; intermediate versioned commits
remain normal development versions.
