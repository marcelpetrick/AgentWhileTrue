<!--
SPDX-FileCopyrightText: 2026 Marcel Petrick

SPDX-License-Identifier: GPL-3.0-or-later
-->

# Debugging: Codex auto-retry never fires at the reset time

Live investigation on 2026-09-10 (CEST, UTC+2). Read-only: no runtime code was
changed and no input was sent to any terminal. All times are local unless
marked `Z`.

## Summary

The retry did not fire for the default Codex profile at 21:52. The user had to
type `continue` by hand, and the watcher did not even notice. It will not fire
for the `codex-dmo` profile at 22:33 either. Six defects combine; the first
three are enough to make an automatic Codex retry impossible today:

| ID | Severity | Defect |
| --- | --- | --- |
| D1 | critical | The prompt's reset time is re-parsed relative to "now" and jumps to tomorrow once it has passed |
| D2 | critical | Codex quota is read from the wrong rollout file, so it is always stale |
| D3 | critical | Full-auto refuses a resume backed only by the reset time, and a blocked Codex never produces fresh quota |
| D4 | high | A fresh pre-limit sample (99%, not "reached") counts as confirmation, so `continue` is sent before the reset |
| D5 | medium | A waiting session is not observed at all until its next check, so manual recovery goes unseen |
| D6 | medium | The retry budget restarts whenever the screen fingerprint changes or the session is rediscovered |

The running TUI and HEAD (0.40.3) have identical decision code (`policy.py`,
`fsm.py`, `quota.py`, `providers/*`); only `cli.py` differs, in dashboard loop
pacing. The analysis therefore applies to the live instance.

## Environment

- `agent-while-true run --observe --all` on pts/3, restarted at 21:47:54 and
  switched to full-auto at 21:48:11 (`mode_changed ... codex_auto_resume=true`).
  The TUI holds the single-instance lock. `doctor` reports `Auto mode OK SAFE`.
- Codex CLI 0.154.0. Watched sessions:
  - default profile: Konsole `konsole-422610`, pts/9, PID 423290 (native child
    423301);
  - `codex-dmo` profile: Konsole `konsole-4469`, pts/5, PID 5571 (native child
    5582).
- Effective config: `reset_grace=60s`, `max_resume_attempts=3`; the Codex
  freshness limit is `DEFAULT_MAX_AGE_SECONDS = 900` (`quota.py:50`).

## Timeline

Default profile (pts/9):

| Time | Event |
| --- | --- |
| 21:50:52 | `ACTIVE -> LIMIT_BLOCKED`, `reset=19:52Z`, `usage-not-confirmed-available`; next check 21:53:00 (reset + grace) |
| 21:53:00 | `resume_refused reason=usage-not-confirmed-available`; next check moves to **2026-09-11 21:53** (D1) |
| ~21:54 | The user types `continue` manually; Codex resumes work |
| 21:56:14 | Dashboard still shows `LIMIT_BLOCKED` while the screen shows `Working`; no `state_change` is logged (D5) |

`codex-dmo` (pts/5):

| Time | Event |
| --- | --- |
| 17:47:42 | Last rate-limit sample with windows: 5h 99%, `rate_limit_reached_type=null` |
| 17:48:00 | `LIMIT_BLOCKED`, `reset=20:33Z` (22:33); refused because the TUI was in observe mode |
| 17:57-21:29 | Machine suspended (`time_jump_detected` at 21:29:08) |
| 21:33:01 | Manual `continue` is blocked again. Codex writes only a `premium` rate-limit event with no windows |
| 21:48:11 | Full-auto enabled; next check shown as 22:34:00 |

Earlier history in the retained log: 12 `resume_sent`, 1 `resume_verified`
(2026-09-08 14:04), 11 `resume_not_verified`.

## Root causes

### D1: the reset time jumps to tomorrow after it passes

`parse_reset` rolls any clock time that is not in the future forward by one day
(`providers/timeparse.py:139-140`, codified by
`tests/test_timeparse.py:25`). Recognition re-parses the visible prompt on every
observation using the current time (`providers/base.py:297`), and the supervisor
stores the resulting `retry_at` as the next check (`fsm.py:436`).

Because `reset_grace` is 60 s, the first re-check always happens after the
printed time, so the rollover is guaranteed rather than a race. Replaying the
installed recognizer on the real prompt text:

| Prompt | Evaluated at | Parsed reset |
| --- | --- | --- |
| `try again at 9:52 PM.` | 21:51:00 | 2026-09-10 21:52 |
| `try again at 9:52 PM.` | 21:53:00 | **2026-09-11 21:52** |
| `try again at 10:33 PM.` | 22:34:00 | **2026-09-11 22:33** |

The authorization then returns `NONE` with `resume_at` one day ahead
(`policy.py:316` is never reached), which is logged as
`usage-not-confirmed-available`.

### D2: Codex quota comes from the wrong rollout file

`find_codex_rollout` returns the first `rollout-*.jsonl` descriptor it meets in
the process tree (`quota.py:193`). Codex 0.154.0 keeps several rollouts open per
process (one per thread/sub-agent), and the lowest file descriptor belongs to an
older, idle thread:

| Session | Picked (lowest fd) | Its last sample | Actively written file | Its last sample |
| --- | --- | --- | --- | --- |
| default | `...T17-22-36` (fd 26) | 17:22:42, 5h 20% | `...T16-49-54` (fd 58) | 21:58:39, 5h 10%, reset 02:53 |
| `codex-dmo` | `...T17-34-30` (fd 36) | 17:44:53, 5h 81% | `...T10-35-13` (fd 43) | 17:47:42, 5h 99%, reset 22:33 |

This is why the dashboard shows Codex quota as `STALE` even while a session is
working, and why the displayed percentages do not match the Codex screen.

### D3: full-auto requires a confirmation that a blocked Codex cannot give

Once the quota is stale, `authorization_for` can only grade `TIME_ONLY` after
the reset plus grace has passed (`policy.py:316`). `evaluate` refuses
`TIME_ONLY` in auto mode with `auto-mode-requires-provider-confirmation`
(`policy.py:368`, tested in `tests/test_policy.py:306`). This is the documented
invariant "A reset timestamp alone does not authorize auto mode."
(`AGENTS.md:34`).

Even with the correct rollout (D2 fixed), a blocked Codex writes no new
windowed rate-limit sample: `codex-dmo`'s blocked attempt at 21:33 produced only
an empty `premium` event. The data therefore goes stale 15 minutes after the
block, long before a typical reset. Under the current invariant, automatic Codex
continuation after a real limit cannot succeed.

### D4: a pre-limit sample authorizes a send before the reset

The last sample before a limit is typically below 100% with
`rate_limit_reached_type=null`, for example 99% at 17:47:42. While that sample
is fresh, it reads as `AVAILABLE` (`EXHAUSTED_PERCENT = 100.0`, `quota.py:45`).
`fresh and AVAILABLE` grants `PROVIDER_CONFIRMED` (`policy.py:308`) before the
prompt's own future reset time is considered. The log shows the result:

- 2026-09-10 12:35:40-12:36:01, `konsole-6314`: prompt reset 14:54, three sends
  about 2h19m early, all `still-blocked`.
- 2026-09-08 14:18:59-14:23:16, `konsole-3131681`: prompt reset 14:49, five
  sends 26-30 minutes early, all not verified.

### D5: waiting sessions are not observed

`_advance` returns `waiting-for-reset` without reading the screen while
`now < next_check_at` (`fsm.py:349-350`). Combined with D1, the session is
unobserved for about 24 hours. A manual `continue`, a new prompt, or a changed
screen is not recorded, and the dashboard keeps showing `LIMIT_BLOCKED`.

### D6: the retry budget can be exceeded

The persisted attempt count is keyed by the idempotency key, which includes the
screen fingerprint (`policy.py:89`). Each sent `continue` changes the screen,
which starts a new key at attempt 0. The in-memory
`attempts_since_success` (`fsm.py:521`) is lost when the session is
rediscovered. On 2026-09-08 the log shows attempts `1, 2, 1, 2, 3`: five sends
in 4m17s despite `max_resume_attempts=3`, with a `previous=DISCOVERED` reset in
between. That episode ran on an older build; the keying is unchanged in HEAD.

### Minor: refusals lack a session field

`resume_refused` events carry no `session=` field (for example 21:53:00).
Attributing them requires correlating with the preceding `state_change`.

## Reproduction

The fake-terminal harness (`tests/harness.py`) running against the installed
package reproduces the live behavior. Setup: full-auto with the Codex opt-in,
tonight's prompt text `try again at 9:52 PM`, and the clock starting at
21:50:52.

Scenario A, stale rollout sample (17:22, 20%), as observed live:

| Clock | Decision | Next check | Sent |
| --- | --- | --- | --- |
| 21:50:52 | `usage-not-confirmed-available` | 09-10 21:53 | 0 |
| 21:53:00 | `usage-not-confirmed-available` | **09-11 21:53** | 0 |
| 21:54:00 | `waiting-for-reset` (not observed) | 09-11 21:53 | 0 |
| 21:59:00 | `waiting-for-reset` (not observed) | 09-11 21:53 | 0 |

Scenario B, fresh sample one minute old (99%, not reached):

| Clock | Decision | Sent |
| --- | --- | --- |
| 21:50:52 | `resume-sent` (before the 21:52 reset) | 1 |
| 21:53:00 | `verify:still-blocked` | 1 |
| 21:54:00 | `resume-sent` | 2 |

The fake screen does not change after a send, so the verify results in
scenario B are expected. The defect is the send before the printed reset.

## Prediction for `codex-dmo` at 22:33

At 22:34:00 the watcher re-reads `try again at 10:33 PM`, parses it as
2026-09-11 22:33 (D1), logs `usage-not-confirmed-available`, and schedules the
next check for 2026-09-11 22:34. No `continue` will be sent.

Observed outcome: pending (to be appended after 22:34).

## Fix directions (not implemented)

1. **D1:** anchor the reset time to the first sighting of the blocking prompt.
   Keep `session.reset_at` while the same blocking prompt remains visible, and
   roll forward only relative to that first sighting. Start with a regression
   fixture that replays tonight: prompt at 21:50:52, `continue` expected at
   21:53:00.
2. **D2:** among all open rollout descriptors in the process tree, use the one
   with the newest windowed rate-limit sample (or the newest mtime), not the
   first one found.
3. **D4:** never send before the prompt's own reset time. A fresh `AVAILABLE`
   sample must not override a printed future reset.
4. **D3 (product decision):** to meet "resume at the reset time, no matter
   what", allow `TIME_ONLY` in full-auto for the exact tested Codex limit
   prompt once its printed reset plus grace has passed. This requires changing
   the `AGENTS.md:34` invariant and `tests/test_policy.py:306`. Vetoes (paid,
   upgrade, reset credit, model downgrade), immediate revalidation, and the
   retry budget stay in force.
5. **D5:** while waiting, perform a cheap read-only observation every 30-60 s
   so manual recovery and new prompts update the state. This must not
   authorize input.
6. **D6:** count attempts per blocking episode (session, process, reset time)
   in the persisted store, independent of the screen fingerprint.
7. Add `session=` to `resume_refused` events.
