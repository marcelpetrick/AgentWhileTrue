<!--
SPDX-FileCopyrightText: 2026 Marcel Petrick

SPDX-License-Identifier: GPL-3.0-or-later
-->

# Agent While True implementation plan

This plan tracks the current implementation and the work that remains. Product
intent and safety requirements live in [vision.md](vision.md); implemented
structure and data flows live in [ARCHITECTURE.md](ARCHITECTURE.md); acceptance
evidence and remaining evidence-dependent work are in [OPEN_ISSUES.md](OPEN_ISSUES.md).

## Current status

Agent While True is a working standalone Python 3.14.x package for KDE Konsole
on Linux. It has no third-party runtime dependencies. The package, local gate,
GitHub quality job, release workflow and container intentionally share that one
runtime; older and unreviewed future Python minors are outside the support
contract.

The implemented baseline includes:

- Konsole sessions are discovered through D-Bus and bound to service, session,
  PID, process start time, and TTY.
- Codex and Claude processes are classified through `/proc`; SSH, containers,
  tmux/screen, shells, ambiguity, and replacement processes fail closed.
- Provider prompt adapters recognize only tested prompt shapes and veto paid,
  upgrade, reset-credit, and quality-changing choices.
- Codex quota is read from its local rollout stream and bound to a validated
  account/rate-limit identity. Bounded main/worker-thread child discovery fixes
  the live default/company-profile `no-rollout-file` failure found on 2026-10-16.
- Claude quota is projected by the owner-only status-line bridge into
  idle-refreshed, hashed-session files bound to PID and process start time.
- Five-hour and weekly usage meters show compact reset countdowns.
- Official Codex API and Claude Code/API status components are polled
  independently on their own `SERVICE_STATUS_INTERVAL` (five minutes by
  default) with bounded, compressed, conditional requests; the dashboard
  re-renders the cached answer without issuing one. OpenAI reads the complete
  components endpoint because its summary omits grouped Codex components.
- Observe, ask, and full-auto modes share the same supervisor and policy gate;
  uppercase `A` deliberately toggles full-auto and back to the previous
  observe or ask mode in the TUI.
- The action lifecycle is persisted as `PLANNED -> SENT -> VERIFIED|FAILED` and
  the TUI retains the latest 50 privacy-preserving history entries.
- Observe-mode rediscovery leaves persisted action and retry state untouched;
  a stale observer cannot prune away the controller's pending intent or spent
  attempts. A two-watcher regression and safety simulation cover this boundary.
  Initial input-lock acquisition reloads state written during session selection.
- Generic and timed Claude automatic-wait confirmations both verify as
  provider-armed waits; current extra-usage, early-reset and lower-priority
  choices are explicit non-automatable vetoes.
- The single-instance lock permits at most one input-capable watcher; a
  dashboard started beside it asks the holder over an owner-only local socket
  to hand input control over (`Shift+A`), and the holder re-arms when the
  dashboard exits.
- Deterministic simulations, package smoke tests, and a live read-only Konsole
  adapter test are part of the release gate.
- All 18 cases named in vision section 40 map permanently to registered
  simulations, including the 30-second reset, 90-second delay, revalidation
  races, lifecycle failures and every prohibited choice.
- The canonical local and CI gate runs strict mypy over the complete runtime
  package in addition to Ruff, ShellCheck and the test/coverage suite.
- The release pipeline publishes a non-root, multi-architecture GHCR safety
  simulator with SBOM and provenance attestations. Its entrypoint exposes only
  offline simulations/help/version and refuses every host-facing command.
- `doctor` reports the validated Linux distribution family, the optional Codex
  app-server capability and the passive Claude quota bridge; optional provider
  warnings stay isolated and do not globally disable the other provider.
- Resume explanations, saved presentation preferences, day/week operational
  summaries, and a responsive scrolling dashboard are implemented; the ordered
  feature plan and validation notes are in [history/nextFeatures.md](history/nextFeatures.md).
- A non-persistent `x` hotkey masks account e-mails in every dashboard view for
  screenshot-safe sharing without altering provider or supervision data.
- A `w` whip hotkey cracks an ASCII bullwhip over the dashboard and types a
  different reminder into each selected session whose fresh observation shows
  a plain working screen, an empty provider composer and quota that is not
  exhausted; five cracks per rolling minute, and never any input in observe
  mode, while paused, or without input control.
- Provider tool-permission prompts are the `APPROVAL_PENDING` state, and a
  non-persistent `y` auto-yes switch answers only the selected one-turn first
  item of exact current Claude or Codex menus, once per appearance, after full
  revalidation; only in full-auto, never in ask or observe mode, while paused
  or without input control. Claude Code 2.1.300's full-window company-policy
  explanations are exact-matched and their visible previews fingerprinted.
  Codex 0.162.1 command, patch, terminal-input, one-time-network and
  turn-permission overlays are covered but never re-sent; persistent choices,
  MCP elicitation, user verification and arbitrary questions remain manual.
- Codex CLI 0.162.1 is the sole verified Codex release. Its percentage-free
  `model reasoning · directory` composer footer is accepted once, while model
  switches, admin requests, spend-cap increases and free trials remain vetoes.
- Codex recovery survives transient Working redraws and watcher restarts without
  losing its reset anchor or replenishing its bounded retry budget. Positive
  activity is confirmed across two observations; the same returning limit
  keeps its spent attempts, and a later date needs absolute provider evidence.
- Measured performance, coverage, licensing and dual-format SBOM gates are
  recorded in [history/maturityPlan.md](history/maturityPlan.md). The observed
  retry and Claude prompt fixes are tracked in
  [history/retryFixPlan.md](history/retryFixPlan.md).

## Acceptance status

The current maintainer follow-up is tracked below. Natural reset acceptance is
witnessed for Codex on 2026-09-18 and Claude on 2026-10-15
([OPEN_ISSUES.md](OPEN_ISSUES.md) O1). The latter used a provider-confirmed
Enter and verified active transition, not merely an automatic-wait selection.
For subsequent provider changes, repeat the same evidence standard:

1. Leave the current version running in full-auto mode with intended sessions
   selected.
2. Allow a supported session to reach a genuine quota limit and reset without
   manually changing its process, prompt, or quota state.
3. Confirm exactly one continuation occurs after the reset grace period.
4. Inspect `agent-while-true logs -n 50` for the matching
   `PLANNED -> SENT -> VERIFIED` lifecycle, or a truthful `FAILED` result.
5. Confirm the log contains identifiers and pattern IDs only, never terminal
   text, prompt content, credentials, or environment values.

This gate must not be forced with a paid choice, model downgrade, fabricated
provider state, or input to an unrelated live session. Simulated reset tests
remain the deterministic regression mechanism.

## Active follow-up: exact approvals, renewal and fixed-model policy

Baseline: `b224585` (2026-10-20). Work on the current branch, use atomic green
commits, and review all follow-up changes against that baseline before delivery.
Do not push, tag, restart an operator dashboard or change provider settings
without the corresponding maintainer request.

- [x] Record the maintainer's invariants in `AGENTS.md`: preserve the same model,
  never select paid choices, and continue quota-blocked work only after the
  relevant budget returns through the normal provider/prompt/identity gate.
- [x] Inspect current live Claude/Codex screens read-only and verify current
  binaries; transcribe only genuinely observed new menus into redacted fixtures.
  The Oct 17–20 MPT audit found successful approvals and explicit policy denials,
  not an unsupported menu. EasyAnalyzer has no recent evidence to extrapolate.
  Installed binaries are Claude 2.1.304 and Codex 0.163.0; existing Claude
  sessions retained 2.1.303. No full permission/model-choice menu was visible,
  so this audit does not certify all newer menus or change `VERIFIED_VERSIONS`.
- [x] Add correlated, privacy-preserving controller/version/mode/auto-yes
  diagnostics and an explicit reason for recognized but unsupported permission
  layouts, including visible dashboard details. Never log command or prompt text.
- [x] Audit and test five-hour, weekly and model-specific budget renewal,
  provider-armed waits, grace periods and bounded retries. Fix demonstrated gaps
  without inferring availability or abandoning other exhausted windows.
  Seven new lifecycle contracts and `budget-renewal` confirm the existing
  runtime gate; no quota-runtime defect required a change.
- [x] Enforce fixed-model and human-only paid decisions in every input path,
  including configurations that request otherwise. Prefer an exact tested
  stay/decline choice only when observed; otherwise show `stay with same model`
  and require the operator, rather than typing into an arbitrary question.
  Legacy opt-ins now reject `true`; model labels add veto-only coverage.
  No full live stay-choice dialog was observed, so automatic model-decline input
  remains evidence-blocked. The message is visible policy, not a typed reply.
- [x] Update usage, architecture and safety documentation; cover behavior with
  unit/lifecycle/dashboard tests, simulations and real offline PTY tests.
- [x] Run the full local pipeline, `/reviewBranch` against `b224585`, fix every
  finding, check `/githubAbout` evidence without changing public metadata, and
  hand off commits, running versions and any evidence-limited manual prompts.
  The review reproduced and fixed a cached diagnostic mismatch for unsettled
  persisted actions after clock-jump schedule invalidation; `PLANNED` and `SENT`
  regressions now match the real approval gate. Final delivery is conditional
  on the canonical gate passing on this exact committed source. Public metadata
  remains unchanged; existing About wording/topics are evidence-backed.
  A subsequent committed-state review also reproduced exact-box diagnostics
  claiming eligibility despite additional paid/model matches. The diagnostic
  singleton-pattern check now mirrors the existing approval gate and reports
  `conflicting-permission-context`; paid/model regressions and a simulation
  prove no input is sent.

Evidence-limited follow-up: a complete live same-model decline dialog and new
affirmative provider-menu layouts were not available. Their automation is not
claimed implemented; capture the actual menu before adding any such action.
The operator's installed service/dashboard is not upgraded as a side effect of
this development task; install the verified version and restart intentionally.

## Maintenance plan

Maintenance is evidence-driven rather than scheduled feature growth.

The follow-up live audit found Claude-dmo active in `hr-doccontrol`, both Codex
profiles active, and no pending approval in those inspected sessions. The
previous MPT agents had exited; an idle shell is not a resumable session. No
additional prompt rule was justified. The audit corrected misleading polling
documentation and recorded discovery latency, bounded retries and manual-only
requests in [USAGE.md](USAGE.md). This is a point-in-time observation, not a
claim to cover every possible provider question.

Overnight monitoring then found a real scoping defect: Claude had successfully
armed its own wait, but the trailing `main` agent panel hid the waiting footer
and verification falsely recorded a resumed turn. An exact-panel-trimmed
candidate is now accepted only for a recognized self-healing wait with no
action; historical actionable menus remain out of scope. Full-screen composer
and permission checks are preserved. A fixture-first recognition regression, persisted lifecycle
test, `claude-wait-agent-panel` simulation and offline PTY dashboard regression
cover the fix. Monitoring completed at 07:00 Europe/Berlin on 2026-10-17.
Claude's wait cleared after its 02:10 reset, with fresh quota and subsequent
usage evidence; no further persistent prompt alert was detected. This does not
prove uninterrupted task progress or expand permission rules or paid choices.
The maintainer requested renewed monitoring later that morning. The repeatable
read-only inspection, evidence, regression and handoff procedure now lives in
`AGENTS.md`; each monitoring period must state its own scope and deadline.

| Trigger | Required response |
| --- | --- |
| Codex or Claude changes a blocking prompt | Capture a real redacted fixture, add a failing recognition test, then update the narrow adapter pattern. |
| Provider quota schema changes | Preserve old valid data until stale, reject malformed/new ambiguity, and add parser fixtures before adapting. |
| Provider status component identity changes | Verify the official public JSON document, update exact IDs, and retain `UNKNOWN` on mismatch. |
| Konsole changes its D-Bus contract | Re-run `doctor` and the opt-in adapter test; do not weaken identity or prompt revalidation. |
| A dependency release is considered | Keep exact development/build pins, verify stable upstream releases, and run the complete pipeline. |
| A live action fails or duplicates | Preserve evidence without terminal contents, add a deterministic lifecycle regression, then fix the smallest responsible layer. |

## Delivery plan for every change

1. Inspect the worktree and preserve unrelated user changes.
2. Make one logical change with tests or evidence proportional to its risk.
3. Bump `src/agent_while_true/version.py` and add the newest matching
   `CHANGELOG.md` section.
4. Run the required pre-commit checks:

   ```bash
   ruff check .
   ruff format --check .
   shellcheck --severity=style *.sh scripts/*.sh
   python3 -m pytest -q
   git --no-pager diff --check
   ```

5. Commit with the established conventional subject style.
6. Before pushing or tagging, run `./localPipeline.sh`, all CLI diagnostics and
   simulations, and the opt-in live Konsole test when KDE Konsole is available.
7. Build and install the wheel in isolation; smoke-test the canonical command.
8. Push only when requested. Tag only a fully verified release and confirm the
   quality, security and release workflows and the published artifacts.

## Deferred scope

The following remain intentionally outside the current product:

- non-KDE terminal automation;
- nested tmux/screen, SSH, container, or root automation;
- paid credit use, purchases, subscription changes, upgrades, reset credits,
  or automatic model downgrades;
- heuristic interpretation of unknown prompts;
- bypassing provider limits or manufacturing quota availability;
- a network daemon protocol, web service, or remote control plane (the local,
  owner-only lock-handover socket excepted);
- predictive capacity estimates without an official source.

Future terminal or provider support must enter through the existing adapter
boundaries and preserve the same identity, quota, prompt, policy, persistence,
and immediate-revalidation gates.
