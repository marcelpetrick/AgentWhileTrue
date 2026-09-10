<!--
SPDX-FileCopyrightText: 2026 Marcel Petrick

SPDX-License-Identifier: GPL-3.0-or-later
-->

# Debugging: Codex auto-retry never fires at the reset time

Live investigation on 2026-09-10 (CEST, UTC+2). Read-only: no runtime code was
changed and no input was sent to any terminal. All times are local unless
marked `Z`.

## Summary

The main feature of Agent While True is to type `continue` into a blocked agent
session as soon as its usage window resets. On 2026-09-10 this did not happen:

- The default Codex profile (pts/9) reset at 21:52. No `continue` was sent. The
  user had to type it by hand, and the watcher did not notice.
- The `codex-dmo` profile (pts/5) resets at 22:33. It will not be resumed
  either (see [Outcome for codex-dmo](#outcome-for-codex-dmo-at-2233)).

Bugs, in fix order:

| ID | Severity | What is wrong |
| --- | --- | --- |
| D1 | critical | The prompt's reset time jumps to tomorrow once it has passed |
| D2 | critical | Codex quota is read from the wrong rollout file and is always stale |
| D3 | critical | Full-auto refuses a resume backed only by the reset time, which is the only evidence a blocked Codex gives |
| D4 | high | `continue` is sent before the reset, based on a pre-limit quota sample |
| D5 | medium | A waiting session is not observed, so manual recovery goes unseen |
| D6 | medium | The retry budget can be exceeded |
| D7 | low | Refusal log events have no session field |

D1, D2 and D3 each prevent an automatic Codex retry on their own. The required
retry behavior is specified in
[Required retry behavior](#required-retry-behavior).

The running TUI and HEAD (0.40.3) have identical decision code (`policy.py`,
`fsm.py`, `quota.py`, `providers/*`); only `cli.py` differs, in dashboard loop
pacing. Every finding therefore applies to the current source.

## Environment

- `agent-while-true run --observe --all` on pts/3, restarted at 21:47:54 and
  switched to full-auto at 21:48:11 (`mode_changed ... codex_auto_resume=true`).
  The TUI holds the single-instance lock. `doctor` reports `Auto mode OK SAFE`.
- Codex CLI 0.154.0. Watched sessions:
  - default profile: Konsole `konsole-422610`, pts/9, PID 423290 (native child
    423301);
  - `codex-dmo` profile: Konsole `konsole-4469`, pts/5, PID 5571 (native child
    5582).
- Effective config: `reset_grace=60s`, `max_resume_attempts=3`,
  `retry_delays=(5, 30, 60)`. The Codex quota freshness limit is
  `DEFAULT_MAX_AGE_SECONDS = 900` (`quota.py:50`).

## Timeline

Default profile (pts/9):

| Time | Event |
| --- | --- |
| 21:50:52 | `ACTIVE -> LIMIT_BLOCKED`, `reset=19:52Z`, `usage-not-confirmed-available`; next check 21:53:00 (reset + grace) |
| 21:53:00 | `resume_refused reason=usage-not-confirmed-available`; next check moves to **2026-09-11 21:53** (D1) |
| ~21:54 | The user types `continue` manually; Codex resumes work |
| 21:56:14 | Dashboard still shows `LIMIT_BLOCKED` while the screen shows `Working`; no `state_change` is logged (D5) |
| 22:04:17 | Codex is idle at its composer; dashboard still shows `LIMIT_BLOCKED` (D5) |

`codex-dmo` (pts/5):

| Time | Event |
| --- | --- |
| 17:47:42 | Last rate-limit sample with windows: 5h 99%, `rate_limit_reached_type=null` |
| 17:48:00 | `LIMIT_BLOCKED`, `reset=20:33Z` (22:33); refused because the TUI was in observe mode |
| 17:57-21:29 | Machine suspended (`time_jump_detected` at 21:29:08) |
| 21:33:01 | Manual `continue` is blocked again. Codex writes only a `premium` rate-limit event with no windows |
| 21:48:11 | Full-auto enabled; next check shown as 22:34:00 |

Retained log history: 12 `resume_sent`, 1 `resume_verified` (2026-09-08
14:04), 11 `resume_not_verified`.

## Bug reports

### D1: the reset time jumps to tomorrow after it passes

**What is wrong.** The Codex prompt says `try again at 9:52 PM.` At the first
check after 21:52, Agent While True parses this as 9:52 PM on the *next day*.
It concludes that usage has not returned and schedules its next check about
24 hours later. The retry never happens.

**What was expected.** The reset stays at 2026-09-10 21:52 for as long as that
prompt is visible. Once it has passed, the retry starts (see
[Required retry behavior](#required-retry-behavior)).

**Evidence.** Log at 21:53:00: `resume_refused reason=usage-not-confirmed-available`.
Replaying the installed recognizer on the real prompt text:

| Prompt | Evaluated at | Parsed reset |
| --- | --- | --- |
| `try again at 9:52 PM.` | 21:51:00 | 2026-09-10 21:52 |
| `try again at 9:52 PM.` | 21:53:00 | **2026-09-11 21:52** |
| `try again at 10:33 PM.` | 22:34:00 | **2026-09-11 22:33** |

**Where.**

- `providers/timeparse.py:139-140`: `parse_reset` rolls any clock time that is
  not in the future forward by one day. `tests/test_timeparse.py:25` codifies
  this.
- `providers/base.py:297`: the prompt is re-parsed on every observation,
  relative to the current time.
- `fsm.py:436`: the resulting `retry_at` becomes the next check.
- The 60 s `reset_grace` guarantees the first re-check is after the printed
  time, so this happens every time, not only in a race.

**Fix.** Anchor the parsed reset to the first sighting of the blocking prompt.
Keep `session.reset_at` while the same blocking prompt remains visible, and roll
forward only relative to that first sighting, never relative to the current
time.

**Regression test.** Fake terminal showing tonight's prompt, first seen at
19:50:52Z. At 19:52:01Z the reset must still be 19:52Z, and attempt 1 of the
retry schedule must be sent.

### D2: Codex quota comes from the wrong rollout file

**What is wrong.** Agent While True reads Codex quota from the first
`rollout-*.jsonl` file descriptor it finds for the process. Codex 0.154.0 keeps
several rollouts open per process (one per thread or sub-agent), and the first
one belongs to an older, idle thread. Codex quota is therefore always `STALE`
on the dashboard, even while the session is working, and the percentages shown
do not match the Codex screen.

**What was expected.** Quota is read from the rollout Codex is actively writing,
the one with the newest rate-limit sample. The dashboard shows live percentages
and `AVAILABLE`/`EXHAUSTED` for a working Codex session.

**Evidence.**

| Session | Picked (lowest fd) | Its last sample | Actively written file | Its last sample |
| --- | --- | --- | --- | --- |
| default | `...T17-22-36` (fd 26) | 17:22:42, 5h 20% | `...T16-49-54` (fd 58) | 21:58:39, 5h 10%, reset 02:53 |
| `codex-dmo` | `...T17-34-30` (fd 36) | 17:44:53, 5h 81% | `...T10-35-13` (fd 43) | 17:47:42, 5h 99%, reset 22:33 |

**Where.** `quota.py:166-199` (`find_codex_rollout`, first match returned at
`quota.py:193`).

**Fix.** Collect every open rollout descriptor in the process tree. Use the one
whose newest windowed rate-limit sample is most recent (fall back to the newest
mtime). Rollouts from other profiles (`CODEX_HOME`) must never be mixed.

**Regression test.** A fake `/proc` with two rollout descriptors, the older
one at the lower fd. The snapshot must come from the newer one.

### D3: full-auto refuses the only evidence a blocked Codex can give

**What is wrong.** After the reset time has passed, a blocked Codex session has
only one piece of evidence that usage returned: the reset time printed in its
own limit prompt. A blocked Codex writes no new quota sample: `codex-dmo`'s
blocked attempt at 21:33 produced only an empty `premium` event. Its quota
therefore goes stale 15 minutes after the block. Full-auto then refuses with
`auto-mode-requires-provider-confirmation`. Even with D1 and D2 fixed, an
automatic Codex retry after a real limit cannot succeed.

**What was expected.** In full-auto, once the printed reset time of the exact
tested Codex limit prompt has passed, `continue` is typed following the retry
schedule. This is the product's main feature and is required "no matter what".
Paid, upgrade, reset-credit and model-downgrade choices stay forbidden.

**Where.**

- `policy.py:316`: with stale quota, the grade can only be `TIME_ONLY`.
- `policy.py:368`: `TIME_ONLY` is refused in auto mode.
- `tests/test_policy.py:306`: tests that refusal.
- `AGENTS.md:34`: the invariant "A reset timestamp alone does not authorize
  auto mode."

**Fix.** Allow `TIME_ONLY` in full-auto when all of these hold:

- the provider is Codex with `allow_codex_auto_resume` set;
- the exact tested limit prompt is visible and carries no other veto;
- the anchored printed reset has passed;
- no fresh quota sample reports an exhausted window with a later reset.

Update `AGENTS.md`, `README.md`, `ARCHITECTURE.md` and
`tests/test_policy.py:306` to match. This is a deliberate change to a
documented safety invariant, requested by the product owner.

**Regression test.** Exact Codex limit prompt, stale quota, printed reset in
the past: `evaluate` must allow the resume in full-auto. With a fresh quota
sample exhausted until later, it must still refuse.

### D4: `continue` is sent before the reset

**What is wrong.** The last quota sample before a limit hit is typically below
100% with `rate_limit_reached_type=null`, for example 99% at 17:47:42. While
that sample is fresh (under 15 minutes old), it reads as `AVAILABLE`, and
`continue` is sent immediately, even though the prompt says the reset is still
in the future. Codex stays blocked, and the attempts are wasted.

**What was expected.** No `continue` is sent before the reset time printed in
the prompt. A fresh `AVAILABLE` sample must not override a printed future
reset.

**Evidence.**

- 2026-09-10 12:35:40-12:36:01, `konsole-6314`: prompt reset 14:54, three sends
  about 2h19m early, all `still-blocked`.
- 2026-09-08 14:18:59-14:23:16, `konsole-3131681`: prompt reset 14:49, five
  sends 26-30 minutes early, all not verified.
- The harness replay (scenario B below) reproduces it on the current code.

**Where.**

- `policy.py:308`: `fresh and AVAILABLE` grants `PROVIDER_CONFIRMED` before
  the prompt's reset time is considered.
- `quota.py:45`: `EXHAUSTED_PERCENT = 100.0`.

**Fix.** When the prompt carries a reset time in the future, no quota grade may
authorize a send before it. The earliest send is the anchored printed reset plus
the first schedule delay.

**Regression test.** Limit prompt with reset at 19:52Z, fresh quota 99% not
reached, clock at 19:50:52Z: no send. Attempt 1 is sent at 19:52:01Z.

### D5: waiting sessions are not observed

**What is wrong.** While a session waits for its next check, it is skipped
entirely: no screen read and no state update. Combined with D1, the session is
unobserved for about 24 hours. The user's manual `continue` at about 21:54 was
never recorded, and the dashboard kept showing `LIMIT_BLOCKED` while Codex was
working and later idle.

**What was expected.** A waiting session is still observed read-only every
30-60 s. A manual `continue`, a new prompt, or a finished task updates its state
and the dashboard within about a minute. Observing never authorizes input.

**Where.** `fsm.py:349-350` (`_advance` returns `waiting-for-reset` without
observing while `now < next_check_at`).

**Fix.** Split observation from action scheduling. Observe at the normal paced
interval; let `next_check_at` gate only the decision to act.

**Regression test.** A session waiting for a reset whose screen changes to
`ACTIVE`: a `state_change` is logged within one observation interval, and
nothing is sent.

### D6: the retry budget can be exceeded

**What is wrong.** The attempt count is keyed by the screen fingerprint.
Each typed `continue` changes the screen, so counting restarts at 0. The
in-memory session counter is lost when the session is rediscovered. On
2026-09-08 the log shows attempts `1, 2, 1, 2, 3`: five sends in 4m17s despite
`max_resume_attempts=3`, with a `previous=DISCOVERED` reset in between. That
episode ran on an older build; the keying is unchanged in HEAD.

**What was expected.** One blocking episode gets exactly the configured
number of attempts (11 in the required schedule), counted persistently,
independent of screen changes and rediscovery.

**Where.** `policy.py:89` (the idempotency key includes the screen
fingerprint); `fsm.py:403-406`, `fsm.py:521` (in-memory
`attempts_since_success`).

**Fix.** Key the attempt budget by the blocking episode: session, process
identity and anchored reset time. Keep it in the persisted state store.

**Regression test.** The screen fingerprint changes after every send, and the
session is rediscovered midway. The total number of sends must equal the budget.

### D7: refusal log events have no session field

**What is wrong.** `resume_refused` events carry no `session=` field (for
example at 21:53:00). With several Codex sessions, a refusal can only be
attributed by correlating it with the preceding `state_change`.

**What was expected.** Every refusal, attempt and verification event names the
session, provider and process.

**Fix.** Add `session=` (and `attempt=` where applicable) to `resume_refused`
and all new retry events.

## Required retry behavior

Requirement stated by the user on 2026-09-10: once the printed reset time has
passed, full-auto must retry `continue` on its own with a growing backoff, and
it must log every attempt.

Proposed schedule. This interprets "1 s, 2 s, 3 s, 8 s, ... ten times, then ten
minutes later" as Fibonacci-style delays and is still to be confirmed:

| Attempt | Delay | Due after the reset |
| --- | --- | --- |
| 1 | 1 s | 0:01 |
| 2 | 2 s | 0:03 |
| 3 | 3 s | 0:06 |
| 4 | 5 s | 0:11 |
| 5 | 8 s | 0:19 |
| 6 | 13 s | 0:32 |
| 7 | 21 s | 0:53 |
| 8 | 34 s | 1:27 |
| 9 | 55 s | 2:22 |
| 10 | 89 s | 3:51 |
| 11 | 10 min | 13:51 |

Rules:

- Attempt 1 is due 1 s after the anchored printed reset. For this path it
  replaces the 60 s `reset_grace`. It depends on the D1 and D3 fixes.
- Each delay starts when the previous attempt has finished, send plus
  verification. When Codex is still blocked it prints a new limit banner
  immediately, so verification can take about 1 s.
- Every attempt passes the full gate first:
  - the same session and process identity;
  - the exact tested limit prompt is still visible;
  - no paid, upgrade, reset-credit, or downgrade veto.

  If the prompt is gone, because Codex resumed or the user typed, the schedule
  stops. No `continue` is ever typed into a working session.
- If Codex prints a new, later `try again at` time (for example a weekly
  limit), the schedule restarts from that time instead of using up attempts.
- The budget belongs to one blocking episode and is persisted (D6). After
  attempt 11 fails, the watcher stops and shows this on the dashboard. The next
  new limit prompt starts a new episode.
- The schedule is configurable, for example
  `RETRY_SCHEDULE=1,2,3,5,8,13,21,34,55,89,600` (seconds).

Logging: every event carries `session=`, `provider=`, `process=`, the episode
key and `attempt=n/11`.

| Event | When |
| --- | --- |
| `resume_retry_scheduled` | An attempt is planned; fields `due_at=` and `delay=` |
| `resume_sent` | `continue` was typed |
| `resume_verified` | Codex left the limit prompt |
| `resume_not_verified` | Still blocked; field `next_retry_at=` |
| `resume_refused` | The gate blocked this attempt; field `reason=` |
| `resume_gave_up` | All 11 attempts failed |

`summary.py` must count the new events alongside the existing ones. An
end-to-end harness test must replay tonight's prompt and assert the send times
21:52:01, 21:52:03, 21:52:06, ..., and the logged event for every attempt.

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

## Outcome for codex-dmo at 22:33

Prediction: at 22:34:00 the watcher re-reads `try again at 10:33 PM`, parses it
as 2026-09-11 22:33 (D1), logs `usage-not-confirmed-available`, and schedules
the next check for 2026-09-11 22:34. No `continue` will be sent.

Observed outcome: pending (to be appended after 22:34).
