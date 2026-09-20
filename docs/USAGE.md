<!--
SPDX-FileCopyrightText: 2026 Marcel Petrick

SPDX-License-Identifier: GPL-3.0-or-later
-->

# Agent While True usage guide

Everything an operator needs after `pipx install`: enabling Konsole input,
choosing sessions and modes, reading the dashboard, configuring the tool,
wiring the Claude quota bridge, and running it as a background service.
[README.md](../README.md) is the short entry page; the safety reasoning behind
each rule is in [vision.md](vision.md) and [ARCHITECTURE.md](ARCHITECTURE.md).

## 1. Enable Konsole input once

Konsole disables input-capable D-Bus calls by default on current releases.
Enable the setting once, then restart Konsole before using ask or auto mode:

```bash
kwriteconfig6 --file konsolerc --group KonsoleWindow \
  --key EnableSecuritySensitiveDBusAPI true
```

This permission lets programs running as your desktop user type into Konsole,
which is why Agent While True layers process identity, exact prompt recognition,
policy, idempotency and immediate revalidation on top. `agent-while-true doctor`
probes the permission with an empty string and blocks auto mode if it is off.

The setting is read when a Konsole process starts. Existing windows remain
input-disabled until Konsole is restarted; keep the current sessions open until
their work is safe, then restart Konsole once and require `doctor` to report
both `Konsole input OK` and `Auto mode OK`. Agent While True cannot bypass this
Konsole boundary and intentionally does not kill or replace existing terminal
sessions.

## 2. See what is running

```bash
agent-while-true status
agent-while-true quota
```

`status` classifies visible Konsole sessions. `quota` is read-only and reports
provider availability, failures, usage percentages, and the reset time for each
known window:

```text
Claude pts/4 PID 769257
  availability: EXHAUSTED
  source:       claude-statusline
  session       100.0%  reset 03:20 (4h)
```

Provider state and terminal state are intentionally separate. A quota may be
available while a terminal is active, or a terminal may show an old limit while
provider data is unavailable. Unknown or stale quota never means available; the
narrow [Codex timed-retry exception](#7-codex-specifics) permits a bounded
trial, not a claim that the provider's quota has refreshed. For Codex, a process
whose rollout stopped updating may use a fresher observation from another live
process only when both rollouts resolve to the same validated local account and
rate-limit identity. Unidentified and different accounts are never combined; the
opaque binding remains in memory and is not logged.

Codex is launched through a Node.js shim on current installations, so Konsole
may label its tab or foreground command `node`. Agent While True walks the child
process tree, classifies the native Codex process, reads quota from that
process, and presents the session as `Codex`.

## 3. Choose sessions and a mode

```bash
agent-while-true run --observe --all   # run the full detection path; never type
agent-while-true run --ask             # select sessions and confirm each action
agent-while-true run --auto            # select sessions; resume policy-approved prompts
agent-while-true run --once            # one tick, plain text, exit (for scripts)
agent-while-true simulate --all        # exercise the built-in danger scenarios
```

Without `--all` a picker lists every Konsole session; only sessions positively
classified as Codex or Claude can be selected, and a plain shell is never
preselected. `fzf` is used when installed (`--no-fzf` disables it). With `--all`
every eligible agent is watched and newly opened agent tabs are picked up on
each rediscovery.

Only one input-capable instance may send input at a time. Starting a second one
does not fail: it watches read-only and arms itself as soon as the incumbent
lets go, so a user service stays startable while a dashboard is open. A watcher
can also be started read-only outright:

```bash
agent-while-true run --observe --all  # press Shift+A to take over full auto
```

`Shift+A` in the dashboard toggles between observe and full-auto. Enabling
full auto this way is an explicit runtime opt-in to Codex composer continuation
(`ALLOW_CODEX_AUTO_RESUME`); paid, upgrade, reset-credit and model-downgrade
policy stays off. Pressing it while running in ask mode also switches to full
auto; restart the command to return to ask mode.

If a background service already owns the lock, `Shift+A` asks it to hand input
control over rather than refusing. The service drops to observe and releases the
lock before it answers, the dashboard takes the lock through the ordinary path,
and the service arms itself again once the dashboard exits - so stopping and
restarting the unit by hand is no longer necessary. A handover is refused while
an action is waiting for verification: press the key again once it has settled.
The channel is a socket in the runtime directory, restricted to the owning user,
and carries the mode, process id and version only.

## 4. The dashboard

On an interactive terminal `run` opens a framed color dashboard inspired by
btop and ollamaFarm. Dark, vivid, CGA, and amber style the whole surface; the
plain theme, `NO_COLOR=1`, or `--no-color` produce ANSI-free output. Colors
carry meaning: green is available/healthy, yellow is waiting or unknown, and
red is exhausted or unsafe.

| Key | Effect |
| --- | --- |
| `-` / `+` | Refresh faster / slower across `0.25 0.5 1 2 3 5 10 30 60` seconds |
| `A` | Toggle observe/full-auto; uppercase activation is an explicit Codex resume opt-in |
| `p` | Pause/resume; pause performs no terminal or quota polling |
| `r` | Rediscover Konsole sessions immediately |
| `t` | Cycle dark, vivid, CGA, amber, and plain themes |
| `x` | Toggle screenshot-safe redaction of account e-mail addresses |
| `e` | Show or hide persisted action/state history |
| `l` | Cycle displayed history through 5, 10, 20, and 50 retained rows |
| `h` or `?` | Toggle the in-dashboard help |
| `d` | Show or hide the selected session's resume explanation |
| `[` / `]` | Select the previous / next session explanation |
| `j` / `k` | Scroll down / up through the dashboard |
| `g` / `G` | Jump to the top / end of the dashboard |
| `q` | Quit and restore the terminal |

Like btop, `+` makes the interval number larger and therefore refreshes more
slowly. Selected sessions use that interval; full Konsole rediscovery runs every
30 seconds or immediately after `r`. Presentation keys redraw cached data and
never multiply terminal or provider polling. Non-interactive observe output
stays ANSI-free and separates scans with a blank line for readable logs.

### Session rows

Every session shows independently recognized terminal state and provider quota.
Red or unknown data does not authorize input; the supervisor fails closed.

- **Account.** A Codex profile home such as `~/.codex-dmo` renders as
  `codex-dmo · business@example.com`, the default as `codex · private@example.com`.
  Claude Code is read the same way from `CLAUDE_CONFIG_DIR`, so `~/.claude-dmo`
  renders as `claude-dmo · business@example.com`. The profile is read from the
  session's own process, never from the watcher's environment, and each profile
  is resolved once per run. Shell aliases cannot be recovered after Zsh expands
  them, but an alias that selects a distinct `CODEX_HOME` or `CLAUDE_CONFIG_DIR`
  leaves that identity on the child process. This display-only identity is
  never written to the log or persistent state.
- **Meters.** Five-hour and weekly used-percentage meters plus time to each
  reset: `[████░] 84% 3h` means 84% used and a reset within three hours.
  Countdowns below 1.5 days use `h`, longer ones `d`.
- **Resets.** `PROMPT RESET` is parsed from the blocking terminal prompt;
  `QUOTA RESET` is the effective reset reported by the provider quota source.
  A reported reset time does not guarantee available quota.
- **Service health.** Public status of the OpenAI Codex API and Anthropic
  Claude Code/API components, fetched independently every five minutes
  (`SERVICE_STATUS_INTERVAL=5m`) with gzip and ETag revalidation, re-rendered
  from cache at the display interval. `UNKNOWN` is shown whenever the network,
  schema, component identity or status is unusable. These are not paid model
  calls.

### Details, history and layout

The `d` detail panel explains the latest decision, recognized pattern IDs,
quota source and age, exhausted windows, and next scheduled check. It labels old
observations as stale; displayed reset/check times never promise a resume. The
panel uses cached evidence and does not read or send terminal input.

The `HISTORY` panel reads the same privacy-preserving event file as
`agent-while-true logs`. It shows 10 entries by default and retains the latest
50 in memory, so expanding it reveals what happened while you were away.
Successful terminal retriggers appear as `resume_sent`, followed by their
verification result. History records fingerprints and pattern IDs, never
terminal text, prompts, credentials, or environment values.

Below 168 columns, session cards replace the wide table. Details, history and
help wrap to fit; `j` / `k` scroll while the navigation footer stays visible,
`g` / `G` jump to the ends, and opening details or help brings that panel into
view. Resizing clamps the scroll position.

Press `x` before taking a screenshot: `codex-dmo · work@example.com` renders as
`codex-dmo · w…@e….com` in every account field, provider data and supervision
identity are untouched, and the toggle resets when the process exits.

### Saved preferences

Theme, history length, and history/detail/help visibility are saved under the
state directory in `preferences.json` (normally
`~/.local/state/agent-while-true/preferences.json`). Changes apply immediately
and survive restart. Invalid files fall back to defaults; save errors appear in
the dashboard. Mode, permissions, selections, pause, scan timing and account
redaction are deliberately never saved. Field-level locked updates stop a second
observe dashboard from overwriting unrelated choices; a failed write is retried
during clean shutdown.

## 5. Configuration

```bash
agent-while-true init     # write the default file if none exists
agent-while-true config   # show the effective configuration
```

The file is `~/.config/agent-while-true/config`, parsed as `KEY=VALUE` data and
never sourced as shell. Precedence is defaults < file < `AGENT_WHILE_TRUE_*`
environment < command line. Durations accept `ms`, `s`, `m`, `h`.

| Key | Default | Meaning |
| --- | --- | --- |
| `MODE` | `ask` | `observe`, `ask`, or `auto` |
| `SCAN_INTERVAL` | `2s` | How often selected sessions are read |
| `USAGE_POLL_INTERVAL` | `60s` | Provider quota refresh cadence |
| `STATUS_POLL_INTERVAL` | `1s` | Dashboard redraw of cached service health |
| `SERVICE_STATUS_INTERVAL` | `5m` | Real requests to the public status APIs (1s–24h) |
| `RESET_GRACE` | `60s` | Extra wait after a nominal reset |
| `MAX_RESUME_ATTEMPTS` | `3` | Attempt budget per prompt outside Codex timed retries |
| `RETRY_DELAYS` | `5s 30s 60s` | Back-off between those attempts |
| `RETRY_SCHEDULE` | `1,2,3,5,8,13,21,34,55,89,600` | Opted-in Codex timed-retry delays (11 attempts) |
| `VISIBLE_LINES` | `40` | Screen lines read per observation |
| `RESUME_AFTER_RESET` | `true` | Master switch for any continuation |
| `ALLOW_CLAUDE_AUTO_WAIT` | `true` | May arm Claude's own "wait, then continue" menu item |
| `ALLOW_CODEX_AUTO_RESUME` | `false` | May type `continue` into Codex's composer |
| `AUTO_ACCEPT_MODEL_DOWNGRADE`, `AUTO_USE_PAID_CREDITS`, `AUTO_BUY_CREDITS`, `AUTO_CONSUME_RESET_CREDIT` | `false` | Never enabled by the supplied configuration |
| `LOG_FILE`, `STATE_DIR`, `RUNTIME_DIR` | XDG defaults | Paths |
| `ALLOW_ROOT`, `USE_FZF` | `false`, `true` | Diagnostics-only root; optional fzf picker |

## 6. Logs and summaries

Logs and state live under `~/.local/state/agent-while-true/`; terminal contents
are never logged. The structured event log records when an action was planned,
sent, verified, refused, retried, or failed:

```bash
agent-while-true logs -n 40
journalctl --user -u agent-while-true.service -f   # service lifecycle/output
```

`agent-while-true summary` reports the last 24 hours, `summary --days 7` a
rolling week. Reports read only the configured event log and its five rotated
backups; they never query terminals or providers. Counts distinguish sent
actions, verified resumptions, armed Claude automatic waits, failures, and
refusal episodes (a changed refusal reason counts again; repeated polls of the
same refusal do not).

Measured blocked and observed session-time sums intervals between consecutive
known observations across watched sessions. It is sampled supervision time, not
provider execution time. Pauses, unknown states, clock jumps and long gaps are
excluded, and waiting without fresh observations is not inferred. Intervals are
flushed about once per minute and on clean exit, so a crash can lose the
unflushed tail. Older logs lack interval/refusal evidence, rotation can remove
events, and multiple observers contribute separate samples — use one watcher for
a non-overlapping report.

## 7. Codex specifics

Codex offers no "press enter to continue" affordance: resuming means typing
into its composer, which is strictly more dangerous than pressing a key, so
Codex continuation stays off until `ALLOW_CODEX_AUTO_RESUME=true` is configured
or `Shift+A` opts in at runtime.

Current Codex versions append Pro and credit-purchase links to the ordinary
usage-limit message. Those links are passive text above a separate composer:
Agent While True may type its continuation into that composer only after the
exact tested limit/reset message and either fresh provider availability or the
opted-in bounded retry gate agree. It never follows or selects a paid link, and
any additional paid, reset-credit, or model-changing prompt vetoes the action.

Codex treats a rapid text-and-Enter stream as a paste and turns that Enter into
a newline. The continuation is therefore wrapped in bracketed-paste markers and
followed by Enter in the same revalidated D-Bus write, so a genuine submit
happens instead of leaving `continue` in the composer.

### Timed retries

With full-auto and `ALLOW_CODEX_AUTO_RESUME=true`, the exact tested Codex limit
banner and empty composer may receive a bounded trial continuation after their
anchored reset. A stale/unknown quota display stays stale/unknown; this
deliberate exception does not apply to Claude.

`RETRY_SCHEDULE=1,2,3,5,8,13,21,34,55,89,600` configures 11 attempts. The first
delay replaces reset grace on this path; subsequent delays begin after the
previous attempt's verification finishes (normally one second plus latency), so
the delays are not absolute offsets from the reset. Near deadlines wake the scan
loop sooner than its ordinary interval.

The same prompt keeps its first observed reset date across midnight and
restarts. On a late first sighting, a matching absolute quota-window timestamp
can corroborate the date even when its availability sample is stale. Without a
reliable date the watcher does not guess a past reset. A pre-limit available
sample never permits input before the printed reset; fresh exhausted later
windows, an unknown exhausted-window reset, or a new post-reset exhaustion
sample still veto the trial.

Attempts are reserved persistently before sending and belong to the session,
process identity and reset episode, not the changing screen fingerprint. An
unsettled `PLANNED` attempt after a crash stays blocked rather than being
replayed; corrupt retry state disables timed trials. After the budget is
exhausted the detail view reports `retry-budget-exhausted`. Manual recovery or
a changed, later reset ends or replaces the episode; waiting sessions remain
observed. Logs include session, process, episode, attempt and next deadline;
summaries count scheduled attempts and exhausted episodes.

## 8. Claude specifics

Claude continuation is a bare Enter, and only when Claude explicitly asks for
it ("usage limit has reset … press enter to continue"). Claude's exact
three-choice limit menu may also be armed so Claude itself continues at reset:
with fresh quota confirming the session is exhausted, auto mode moves from the
visibly selected first item to the exact "wait here, then continue
automatically" item and confirms it. It never selects "upgrade your plan", and
any different menu, cursor position, or unknown quota fails closed. Set
`ALLOW_CLAUDE_AUTO_WAIT=false` to disable arming.

![Claude Code session-limit menu](../media/claude_out_of_quota.png)

### Quota bridge

Claude Code exposes quota data only to its configured status-line command. The
bridge is the supplied `scripts/claude-statusline-proxy.sh` — not another
package, daemon, plugin, or network service. It receives that JSON, copies only
the usage windows, reset timestamps, a hashed session identifier, and the
Claude process identity to Agent While True's state directory, then runs your
existing status line with the original JSON. Each selected session accepts only
the quota file bound to its exact PID and process start time.

Without it, `agent-while-true quota` reports Claude as `UNKNOWN` with
`no-statusline-file`. Prompt detection still works, but automatic mode will not
guess that quota is available.

Install and chain the supplied file in one command:

```bash
scripts/install-claude-bridge.sh
```

The installer copies the proxy, backs up `~/.claude/settings.json`, preserves
the existing status-line command and other status-line settings, and configures
a 60-second refresh so quota stays current while Claude is idle.

To do it by hand, install the one supplied file and point Claude's `statusLine`
at it, passing the previous command (if any) through
`AGENT_WHILE_TRUE_STATUSLINE_CHAIN`:

```bash
install -Dm755 scripts/claude-statusline-proxy.sh \
  ~/.local/share/agent-while-true/claude-statusline-proxy.sh
```

```json
{
  "statusLine": {
    "type": "command",
    "command": "AGENT_WHILE_TRUE_CLAUDE_PID=$PPID AGENT_WHILE_TRUE_STATUSLINE_CHAIN=~/.claude/my-statusline.sh ~/.local/share/agent-while-true/claude-statusline-proxy.sh",
    "refreshInterval": 60
  }
}
```

Omit `AGENT_WHILE_TRUE_STATUSLINE_CHAIN=…` when there was no status line before.
Restart Claude Code if it does not reload the setting, wait for one status-line
render, then verify without enabling automation:

```bash
agent-while-true quota
ls -l ~/.local/state/agent-while-true/quota/claude-*.json
```

The bridge writes one owner-only, atomically replaced quota document per Claude
session. Legacy global files are display-only and cannot authorize an action for
a selected process. Bridge failures never prevent the existing status line from
running.

## 9. Background service

Install and enable the supplied observe-only user service from a checkout:

```bash
scripts/install-user-service.sh
systemctl --user status agent-while-true.service
```

The shipped service is observe-only: it discovers new agent tabs but can never
send input. After validating `doctor`, `quota`, observe mode and the
simulations, install the managed auto-mode drop-in — optionally with the
separate Codex composer opt-in:

```bash
scripts/install-user-service.sh --auto
scripts/install-user-service.sh --auto --allow-codex-auto-resume
```

Both forms enable and start `agent-while-true.service` immediately and on
future desktop logins. Running the installer without `--auto` restores the
managed observe-only configuration; `--uninstall` removes the service and its
drop-in.

## 10. One-shot full-auto launcher

```bash
./fullAutoMode.sh          # or --noRun to set up and check without opening the TUI
```

From a checkout, the launcher runs the complete release gate, installs that
verified wheel with `pipx`, creates the default configuration if needed,
requires `doctor` to pass, shows live status and quota, and opens the auto-mode
dashboard for all eligible sessions. Invoking it explicitly opts Codex into
composer continuation; paid, upgrade, reset-credit and model-downgrade actions
remain forbidden. If another input-capable watcher already owns the lock it
stays in control and the launcher opens an observe-only dashboard instead, where
`Shift+A` asks that watcher to hand input control over.
