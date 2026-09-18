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
supervised, no fabricated state, no manual input to the chosen session:

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
accepted build therefore differs from the v0.45.6 release; tagging it is the
remaining release step.

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

1. **High — publish the accepted build.** Run `./localPipeline.sh` on the
   accepted commit, tag it, and verify the release workflow and SBOM hashes.
2. **Medium — witness the Claude path if it ever arises.** Keep the service
   under observation; a Claude session that does not self-heal (reset more
   than 24 h out, or backgrounded) is the only case that needs the supervisor.
3. **Ongoing — work the fix backlog below in impact order**, F0 layer 2 first.

## Fix backlog (evidence from the 2026-09-18 review and v0.45.6 live run)

Ordered by impact. Each is a separate `fix` commit with its own regression test;
none weakens a safety gate.

| ID | Sev | Where | Defect | Evidence |
| --- | --- | --- | --- | --- |
| F0 | HIGH (layer 1 fixed in 0.45.7; layer 2 open) | `policy.py:353` | Prose that merely *quotes* the affordance strings is recognised as a live prompt: a Claude Code session whose conversation contained "usage limit has reset … press enter to continue" went `READY_TO_RESUME`, and the gate grants `PROVIDER_CONFIRMED` on that state alone, with fresh `AVAILABLE` quota and no preceding limit state. Only a coincidental `claude/self-healing` veto in the same paragraph stopped an Enter into an unrelated live session. Fix both layers: require a preceding `LIMIT_BLOCKED`/`WAITING_FOR_RESET` observation on the same process before `READY_TO_RESUME` may authorise, and anchor `claude/ready-press-enter` to Claude's rendered affordance line rather than free text. Add the fixture first. | Live 2026-09-18 14:52:57–58: `konsole-102315/Sessions/1` (this reviewer's own Claude Code tab, pid 1841862) `ACTIVE → READY_TO_RESUME`, `resume_refused reason=provider-resumes-itself`, back to `ACTIVE` at 14:53:06. No input was sent. |
| F1 | MEDIUM | `cli.py:398` | Non-interactive auto mode renders the full dashboard frame on every scan; observe mode prints one line per session. | Service journal: 29 frames/min, ~980 lines/min, 605.8 MB in four days of the 0.44.3 service. |
| F2 | MEDIUM | `terminal/konsole.py:166` | `getAllDisplayedTextList` transfers the whole scrollback per observation; only the last `VISIBLE_LINES` are kept. Use `getDisplayedTextList` or otherwise bound the read. | Code reading; vision §14 and `terminal/base.py:9` forbid retaining scrollback. Magnitude depends on the Konsole history limit. |
| F3 | MEDIUM | `fsm.py:621` | `_record_state` maps only four of classify's fourteen blocker strings to `UNSUPPORTED`; every other non-agent classification leaves the previous state on screen. | Live 14:30:14–14:30:16: tab held a shell (`idle-shell` refused) while the row still read `ACTIVE`. Input was correctly refused. |
| F4 | LOW | `ui.py:195` | Countdown switches from hours to days at 1.5 days (36 h, `ceil`), so 37–47 h renders as `2d` while 34 h renders as `34h`. Wanted: hours below 48 h, days from 2 d. Align `format_reset` (`+Nd` from 24 h) with the same boundary. | Screenshot 2026-09-18 14:37: weekly resets `2d`, `2d`, `2d`, `7d`, `34h` side by side. |
| F5 | LOW | `cli.py:295` | `Shift+A` is a two-state toggle over three modes: from ask it escalates to full-auto with the Codex opt-in and can never return to ask. | Code reading; USAGE §3 documents the current behaviour. |
| F6 | LOW | `state_store.py:153` | Retry episodes are never expired; settled episodes accumulate in `state.json` and are rewritten with `fsync` on every save. | Code reading. |
| F7 | LOW | `quota.py:360` | Each Codex rollout tail (256 KiB) is parsed at least four times per tick (`_warm_quota_sources` + `observe`, `find_codex_rollout` + `_last_rate_limits`). Cache per `(path, size, mtime_ns)`. | Code reading. |
| F8 | LOW | `providers/timeparse.py:69` | `_WEEKDAY_RE` matches the words "sat" and "sun"; fails safe (waits longer). Needs a real fixture before the recognizer changes. | Code reading; no live occurrence. |

## Known conservative boundaries

These are deliberate limits, not pending implementation bugs:

- A clock-only prompt first observed after its apparent reset cannot be dated
  retroactively unless persisted first-sighting or corroborating absolute quota
  evidence exists. The supervisor refuses instead of guessing a date.
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
- coverage regression: restore the enforced 91% combined floor with meaningful
  failure-path tests, prioritizing process classification and Konsole errors;
- dependency advisory: update the exact development/build pin and run the full
  source, wheel, audit, and SBOM gates.

Remove an item from the open section only when its stated evidence exists. Keep
the resolution in the changelog or history rather than allowing this file to
grow into another archive.
