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

Priority: critical acceptance evidence. Implementation status: complete in the
v0.45.6 release candidate; natural live acceptance remains outstanding.

The released build must supervise an intended Codex or Claude session through a
real quota exhaustion and reset, without fabricated quota data, process
replacement, unsafe input, or a paid/quality-changing choice. Acceptance needs
all of the following:

- run v0.45.6 or later in full-auto mode with only intended sessions selected;
- observe a supported, exact blocking prompt and a naturally eligible reset;
- confirm exactly one policy-approved continuation is sent;
- confirm the lifecycle is `PLANNED -> SENT -> VERIFIED`, or records an honest
  `FAILED` result without an unsafe duplicate;
- inspect the latest structured events with `agent-while-true logs -n 50` and
  verify they contain identifiers and pattern IDs, never terminal text, prompt
  content, credentials, tokens, email addresses, or environment values.

Correct refusal for stale, unknown, malformed, conflicting, or unsupported
evidence does not satisfy this acceptance item. It remains the correct runtime
behavior and must not be weakened merely to close the test.

## Impact-ordered execution plan

1. **Critical — put the verified release under observation.** Install the
   published v0.45.6 wheel whose hash matches the release SBOM, run `doctor`,
   `status`, `quota`, and `simulate --all`, then start the existing explicitly
   opted-in full-auto user service. Do not disturb live agent processes.
2. **Critical — capture the natural reset.** Let that service observe only the
   already intended eligible sessions until one reaches an exact supported
   limit and naturally resets. Do not fabricate evidence or manually continue
   the chosen session during the acceptance window.
3. **Critical — validate safety and uniqueness.** Correlate privacy-safe
   provider/session/process/episode/attempt identifiers; require one permitted
   send and a verified recovery, with no duplicate, paid, or quality-changing
   action. A correct refusal leaves O1 open for the next genuine event.
4. **High — close and publish the evidence.** Recheck the latest structured
   events for sensitive-content absence, record timestamps and the released
   version here, rerun the relevant release checks, and commit the completed
   acceptance record. If the live event exposes a defect, add a redacted fixture
   and regression test before the smallest safety-preserving fix.

## Fix backlog (evidence from the 2026-09-18 review and v0.45.6 live run)

Ordered by impact. Each is a separate `fix` commit with its own regression test;
none weakens a safety gate.

| ID | Sev | Where | Defect | Evidence |
| --- | --- | --- | --- | --- |
| F0 | HIGH | `providers/claude.py:124`, `policy.py:353` | Prose that merely *quotes* the affordance strings is recognised as a live prompt: a Claude Code session whose conversation contained "usage limit has reset … press enter to continue" went `READY_TO_RESUME`, and the gate grants `PROVIDER_CONFIRMED` on that state alone, with fresh `AVAILABLE` quota and no preceding limit state. Only a coincidental `claude/self-healing` veto in the same paragraph stopped an Enter into an unrelated live session. Fix both layers: require a preceding `LIMIT_BLOCKED`/`WAITING_FOR_RESET` observation on the same process before `READY_TO_RESUME` may authorise, and anchor `claude/ready-press-enter` to Claude's rendered affordance line rather than free text. Add the fixture first. | Live 2026-09-18 14:52:57–58: `konsole-102315/Sessions/1` (this reviewer's own Claude Code tab, pid 1841862) `ACTIVE → READY_TO_RESUME`, `resume_refused reason=provider-resumes-itself`, back to `ACTIVE` at 14:53:06. No input was sent. |
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
