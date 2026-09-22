<!--
SPDX-FileCopyrightText: 2026 Marcel Petrick

SPDX-License-Identifier: GPL-3.0-or-later
-->

# Open issues and acceptance work

This is the single authoritative list of unresolved Agent While True work. It
consolidates the former root-level debugging and task documents. Completed
implementation plans remain under `docs/history/` as evidence, not as active
backlogs.

## Open acceptance issue

### O1 — Validate one natural provider reset end to end

Status: **accepted for Codex on 2026-09-18** with a natural reset; the Claude
path remains unwitnessed (Claude Code has resumed itself since 2.1.234, so a
Claude event may never need the supervisor).

Evidence, build 0.45.9 (commits `ac34510`, `1b51d0c`, `7846733` on top of the
v0.45.6 release), full-auto user service with the Codex opt-in, six sessions
supervised, no fabricated state, no manual input to the chosen session. The
full write-up is [history/0.45.9_resume_trigger_report.md](history/0.45.9_resume_trigger_report.md):

| Time (CEST) | Event |
| --- | --- |
| 14:56:30 | `codex-dmo` (Codex CLI 0.154.0) `LIMIT_BLOCKED`, "try again at 3:23 PM" anchored to `2026-09-18T13:23:00Z` |
| 15:01:36 | retry episode created after the 0.45.8 deploy; attempt 1/11 due `13:23:01Z`; pre-reset refusal `other-limit-still-exhausted:session` from fresh rollout quota |
| 15:23:01.175 | `resume_sent` attempt 1/11, `TEXT_THEN_ENTER`, `TIME_ONLY`; `PLANNED` persisted before the send |
| 15:23:02–15:23:09 | attempts 1–3 `resume_not_verified` → `FAILED still-blocked` (Codex accepted the text, hit the limit again); attempts 2 and 3 re-planned only after the previous one settled |
| 15:23:16.528 | `resume_sent` attempt 4/11 |
| 15:23:17.600 | `resume_verified result=resumed`; episode `completed`, `attempts=4`, no pending key |

`agent-while-true logs` for the window contains provider, session, process,
episode and attempt identifiers, screen fingerprints, pattern IDs and reasons
only — no terminal text, prompt content, credentials, e-mail addresses or
environment values.

Two defects were found by the same run *before* the event and fixed
fixture-first: the 0.45.6 recognizer did not accept the Codex 0.154.0 composer
under its animated particle chrome (no episode would have been created and the
session would have waited past its reset), and an unrelated Claude Code
session quoting the reset affordance was read as `READY_TO_RESUME` (F0). The
accepted build therefore differs from the v0.45.6 release, and was published as
`agentwhiletrue-v0.45.9`.

The original acceptance criteria are kept below for the Claude path.

The released build must supervise an intended Codex or Claude session through a
real quota exhaustion and reset, without fabricated quota data, process
replacement, unsafe input, or a paid/quality-changing choice. Acceptance needs
all of the following:

- run v0.45.6 or later in full-auto mode with only intended sessions selected;
- observe a supported, exact blocking prompt and a naturally eligible reset;
- confirm the policy-approved continuation is sent, and for the bounded Codex
  schedule that every further attempt is planned only after the previous one
  settled as an honest `FAILED`;
- confirm the lifecycle ends `PLANNED -> SENT -> VERIFIED`, or records an honest
  `FAILED` result without an unsafe duplicate;
- inspect the latest structured events with `agent-while-true logs -n 50` and
  verify they contain identifiers and pattern IDs, never terminal text, prompt
  content, credentials, tokens, email addresses, or environment values.

Correct refusal for stale, unknown, malformed, conflicting, or unsupported
evidence does not satisfy this acceptance item. It remains the correct runtime
behavior and must not be weakened merely to close the test.

## Impact-ordered execution plan

1. **Done — the accepted build is published.** Tagged and released as
   `agentwhiletrue-v0.45.9`; later releases follow the same verified path.
2. **Medium — witness the Claude path if it ever arises.** Keep the service
   under observation; a Claude session that does not self-heal (reset more
   than 24 h out, or backgrounded) is the only case that needs the supervisor.
3. **Ongoing — work the fix backlog below in impact order.** F0 (a quoted
   reset affordance authorising an Enter) is closed: the pattern is anchored
   since 0.45.9 and the gate requires a preceding limit since 0.50.1. F1, F3,
   F4, F5, F6 and F7 are fixed in 0.50.2-0.50.7. F2 was not a defect: on
   2026-09-22 `getAllDisplayedTextList` returned 76-80 lines - the displayed
   screen - in each of ten live Konsole sessions with a 1000-line history, and
   `getDisplayedTextList` offsets count from the top of that same buffer, so
   there is no scrollback transfer to bound. F8 waits for a real fixture.

## Fix backlog (evidence from the 2026-09-18 review and v0.45.6 live run)

Ordered by impact. Each is a separate `fix` commit with its own regression test;
none weakens a safety gate.

| ID | Sev | Where | Defect | Evidence |
| --- | --- | --- | --- | --- |
| F8 | LOW | `providers/timeparse.py:69` | `_WEEKDAY_RE` matches the words "sat" and "sun"; fails safe (waits longer). Needs a real fixture before the recognizer changes. | Code reading; no live occurrence. |

## Known conservative boundaries

These are deliberate limits, not pending implementation bugs:

- A clock-only prompt first observed after its apparent reset cannot be dated
  retroactively unless persisted first-sighting or corroborating absolute quota
  evidence exists. The supervisor refuses instead of guessing a date.
- Claude's "usage limit has reset · press enter to continue" authorises input
  only on a process this supervisor instance saw held at a limit. The sighting
  is not persisted, so a restart while Claude waits leaves that prompt to a
  human rather than trusting a screen the supervisor cannot tie to a limit.
- A persisted `PLANNED` action left across an ambiguous crash window is not
  automatically repeated. It needs human inspection because the terminal API
  cannot prove whether input reached the process.
- KDE Konsole exposes no atomic compare-screen-and-send operation. Agent While
  True minimizes the remaining race by making the last external check a fresh
  process-identity read and performing no persistence between it and `sendText`.
- Unsupported terminals, SSH, containers, tmux/screen, unknown prompt shapes,
  purchases, paid credits, upgrades, reset credits, and model downgrades remain
  intentionally outside automation.

## Resolved debugging issues

The former D1–D8 incident report is summarized here so old failures are not
mistaken for current work:

| ID | Resolution in v0.42.x |
| --- | --- |
| D1 | Clock-only resets are anchored to first sighting or corroborated absolute evidence. |
| D2 | The freshest valid windowed quota event is selected across same-profile open Codex rollouts. |
| D3 | Explicitly opted-in Codex sessions may use bounded timed trials after an anchored reset; quota remains unknown/stale when it is unknown/stale. |
| D4 | A printed future reset gates Codex input even when an older quota sample says available. |
| D5 | Waiting sessions continue to be observed so manual recovery becomes visible. |
| D6 | A process-bound eleven-attempt episode budget persists across screen changes and restarts. |
| D7 | Retry lifecycle logs identify provider, session, process, episode, and attempt. |
| D8 | Claude recognition is scoped to the active prompt region and ignores logged paid-pattern identifiers while retaining real paid-choice vetoes. |

Regression coverage includes changed fingerprints, restart recovery, the full
retry budget, final revalidation cancellation, stale/fresh quota conflicts,
Claude process-bound quota files, timed automatic-wait verification, current
paid/quality vetoes, and log-text false positives. Release evidence is recorded
by the v0.45.6 tag workflow; the natural reset remains a separate acceptance
event and cannot be replaced by deterministic tests.

## Maintenance triggers

New issues belong in this file only when evidence makes them actionable:

- changed provider prompt or quota schema: capture a redacted real fixture and
  add the failing regression before changing recognition;
- changed Konsole D-Bus behavior: reproduce with `doctor` and the opt-in live
  adapter test without sending a real continuation;
- failed or duplicate live action: preserve privacy-safe lifecycle identifiers,
  add a deterministic regression, and fix the smallest responsible layer;
- coverage regression: restore the enforced 98% combined floor with meaningful
  failure-path tests, prioritizing process classification and Konsole errors;
- dependency advisory: update the exact development/build pin and run the full
  source, wheel, audit, and SBOM gates.

Remove an item from the open section only when its stated evidence exists. Keep
the resolution in the changelog or history rather than allowing this file to
grow into another archive.
