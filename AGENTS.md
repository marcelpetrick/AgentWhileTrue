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
- Bind a selection to Konsole service/session plus PID, process start time, and
  TTY; never transfer an interactive selection to a replacement process.
- Re-read session identity, process class, visible prompt, and policy directly
  before `sendText`.
- Never automate upgrades, purchases, paid credits, reset credits, or model
  downgrades.
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
- Claude Code permission prompts are never resume prompts. Only the operator's
  dashboard auto-yes switch (`y`) answers one: off at every start, never
  persisted, only in full-auto - never in ask or observe mode, while paused or
  without input control;
  only an exact tested permission menu - a whole-row "Do you want to ...?",
  the cursor on `1. Yes`, an optional `2. Yes, and ...`, a final `No` - alone
  on the screen and unchanged since the scan, once per appearance, by Enter on
  item 1. The identical box still on screen 3 seconds after its answer counts
  as an Enter that did not land and gets exactly one more Enter, through the
  full revalidation; if it stays after that too it is reported once and left
  to the operator. Never select a "Yes, and ..." item: those change provider
  settings or session modes.
- Never log terminal contents, environment values, credentials, or prompt text.
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
  reason; Python 3.12+ standard library is the baseline.
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
