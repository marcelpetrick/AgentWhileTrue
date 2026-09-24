<!--
SPDX-FileCopyrightText: 2026 Marcel Petrick

SPDX-License-Identifier: GPL-3.0-or-later
-->

# Agent While True architecture

This document describes the implemented architecture. It uses the C4 model to
move from the surrounding systems to the runtime components, followed by the
safety-critical action flow. The diagrams use standard Mermaid flowcharts so
they render on GitHub without a C4-specific plugin.

## System context

```mermaid
flowchart LR
    user["Person<br/>Desktop user"]
    awt["Software system<br/>Agent While True<br/>Observes quota and safely resumes blocked agents"]
    konsole["External system<br/>KDE Konsole<br/>Session discovery, bounded screen reads, guarded input"]
    codex["External system<br/>Codex CLI<br/>Terminal prompts and local rollout quota data"]
    claude["External system<br/>Claude Code<br/>Terminal prompts and status-line quota data"]
    openai["External system<br/>OpenAI Statuspage<br/>Codex API component health"]
    anthropic["External system<br/>Claude Statuspage<br/>Claude Code and API component health"]

    user -->|selects sessions, chooses mode, reviews history| awt
    awt -->|reads sessions; conditionally sends exact input| konsole
    konsole -->|hosts| codex
    konsole -->|hosts| claude
    codex -->|local process and rollout evidence| awt
    claude -->|local process and status-line evidence| awt
    openai -->|public JSON status| awt
    anthropic -->|public JSON status| awt
```

Agent While True does not call paid model APIs. Provider quota, public service
health, and terminal prompt state are separate evidence sources. No single
source authorizes input by itself.

## Containers

```mermaid
flowchart TB
    user["Desktop user"]
    systemd["systemd user service<br/>Optional background lifecycle"]

    subgraph awt["Agent While True"]
        cli["CLI and TUI<br/>Python<br/>Commands, selection, modes, dashboard"]
        supervisor["Supervisor<br/>Python<br/>Observation and action state machine"]
        adapters["Terminal and provider adapters<br/>Python<br/>Konsole, Codex, Claude"]
        quota["Quota readers<br/>Python<br/>Codex rollout and Claude bridge files"]
        health["Health monitor<br/>Python threads<br/>Independent conditional HTTP polling"]
        policy["Policy gate<br/>Python<br/>Fail-closed authorization"]
        state["State and event store<br/>Owner-only local files<br/>Lifecycle, retries, history"]
        bridge["Claude status-line bridge<br/>Shell<br/>Minimal quota projection"]
    end

    konsole["KDE Konsole D-Bus"]
    proc["Linux /proc"]
    localdata["Codex rollout and Claude status-line data"]
    statuspages["Provider public status APIs"]
    claudecli["Claude Code status-line hook"]

    user --> cli
    systemd --> cli
    cli --> supervisor
    supervisor --> adapters
    supervisor --> quota
    supervisor --> policy
    supervisor --> state
    adapters --> konsole
    adapters --> proc
    quota --> localdata
    health --> statuspages
    health --> cli
    claudecli --> bridge
    bridge --> localdata
```

The runtime package has no third-party dependencies. Shell is limited to the
Claude bridge, installation helpers, and quality/release integration.

Presentation preferences live in a separate, versioned owner-only file and
can restore only theme, history length and panel visibility. The detail panel
reads cached decision/observation metadata; it never evaluates authorization.
Responsive rendering and viewport navigation operate solely on presentation.
The screenshot-redaction toggle masks account e-mails at every rendering site,
never changes supervision identity, and is deliberately excluded from saved
preferences so a later run cannot silently inherit its privacy display state.
Persisted presentation fields are merged under an owner-only file lock and
atomically replaced. This prevents concurrent observe dashboards from losing
unrelated updates; transient failures remain dirty and are retried on shutdown.

`metrics.py` batches intervals between consecutive known observations, excluding
pauses and gaps. `summary.py` streams retained structured logs, including rotated
backups, to report event counts and sampled session-time. Both are independent
of the persisted action lifecycle; reports explicitly describe partial coverage.

## Runtime components

```mermaid
flowchart LR
    command["cli.py<br/>Command dispatch and runtime mode toggle"]
    picker["picker.py<br/>Discovery and explicit selection"]
    tui["tui.py + ui.py + whip.py<br/>Input handling, rendering, whip animation"]
    fsm["fsm.py<br/>Supervisor and session state"]
    classify["proc.py + classify.py<br/>Process identity and safety classification"]
    terminal["terminal/konsole.py<br/>Bounded reads and sendText"]
    provider["providers/*<br/>Exact prompt recognition and resume action"]
    quota["quota.py<br/>Freshness, windows, account binding"]
    health["service_health.py<br/>Strict component health cache"]
    policy["policy.py<br/>Authorization decision"]
    store["state_store.py + logging_setup.py<br/>Idempotency and redacted history"]

    command --> picker
    command --> tui
    command --> fsm
    picker --> classify
    picker --> terminal
    fsm --> classify
    fsm --> terminal
    fsm --> provider
    fsm --> quota
    fsm --> policy
    fsm --> store
    health --> tui
    quota --> tui
    store --> tui
```

The abstractions in `terminal/base.py` and `providers/base.py` keep terminal
transport separate from provider-specific prompts. Deterministic fake-terminal
tests exercise the same supervisor and policy paths as the Konsole adapter.

Claude's status-line bridge hashes the stable Claude session identifier and
writes one owner-only quota document per session. The document also carries the
Claude PID and kernel process start time captured from the status-line parent;
`quota.py` requires both to match the selected process. The installer requests
a 60-second status-line refresh while preserving existing status-line options,
preventing idle quota evidence from silently crossing the 15-minute freshness
limit. A legacy unbound file may be displayed only when no process is supplied
and can never authorize an action for a selected session.

## Guarded resume flow

```mermaid
flowchart TD
    scan["Discover selected Konsole session"] --> identity{"Same service, session, PID,<br/>start time, and TTY?"}
    identity -- no --> refuse["Refuse and record reason"]
    identity -- yes --> process_type{"Supported local Codex<br/>or Claude process?"}
    process_type -- no --> refuse
    process_type -- yes --> prompt{"Exact current prompt<br/>recognized without veto?"}
    prompt -- no --> refuse
    prompt -- yes --> quota{"Provider confirmation or opted-in<br/>bounded Codex timed-trial gate?"}
    quota -- no or unknown --> refuse
    quota -- yes --> mode{"Mode and policy permit<br/>the exact action?"}
    mode -- no --> refuse
    mode -- yes --> planned["Persist PLANNED with idempotency key"]
    planned --> revalidate{"Immediately re-read identity,<br/>process class, prompt, and policy"}
    revalidate -- changed --> failed["Persist FAILED; send nothing"]
    revalidate -- unchanged --> send["Send one exact action through Konsole"]
    send --> sent["Persist SENT"]
    sent --> verify{"Expected prompt transition observed?"}
    verify -- yes --> verified["Persist VERIFIED"]
    verify -- no --> retry{"Retry budget and fresh gate still valid?"}
    retry -- yes --> revalidate
    retry -- no --> failed
```

Observe mode never reaches `PLANNED` or `sendText`. Unknown/stale quota remains
unknown/stale; it does not become available. The sole trial exception is the
owner-requested exact Codex limit composer after an anchored reset, with the
explicit Codex opt-in, persistent episode budget and no fresh contradictory
limit. Claude and other actions still require provider confirmation.

Waiting gates actions, not observations. Each normal scan updates displayed
state; action/verification deadlines can wake the loop sooner. Codex reset
anchors are bound to the selected process and reset hint; a later reset creates
a separate episode. All open same-profile rollouts are considered for quota,
using newest valid windowed evidence rather than file-descriptor order.

## Operator whip

The dashboard's `w` key is the one input path an operator starts by hand. It
is deliberately outside the resume lifecycle: a crack is a single attempt per
session and is never planned, persisted or retried, so a restart cannot repeat
it. It still passes its own revalidating gate in `Supervisor.whip`:

```mermaid
flowchart LR
    key["w pressed"] --> rate{"under 5 cracks in the last 60 s?"}
    rate -->|no| cool["cooldown; nothing drawn or read"]
    rate -->|yes| anim["ASCII crack animation"]
    anim --> armed{"unpaused and holding the input lock?"}
    armed -->|no| air["cracked in the air; nothing read or typed"]
    armed -->|yes| each["for each selected session"]
    each --> gate{"fresh observation: not unsafe, nothing in flight,<br/>same identity, automatable, ACTIVE with no prompt matched,<br/>composer visibly empty, quota not EXHAUSTED"}
    gate -->|no| skip["skipped, reason logged"]
    gate -->|yes| phrase["next phrase from this crack's order"]
    phrase --> reread{"foreground process re-read unchanged?"}
    reread -->|no| skip
    reread -->|yes| send["sendText: bracketed paste + Enter"]
```

"Composer visibly empty" is provider-specific: Codex's composer row holds
nothing but its placeholder and only its footer follows; Claude's empty cursor
row must sit directly on its input box's closing rule, so a multi-line draft
begun with Shift+Enter is skipped too. Quota is used the other way round from a
resume: exhausted quota blocks a crack, while unknown quota does not, because a
reminder asks for no usage that is not already being spent. Each crack offers
all forty phrases in an order that puts recently delivered ones last, so every
session reached gets a different line. The log records the phrase index, never
its text.

## Persisted action lifecycle

```mermaid
stateDiagram-v2
    [*] --> PLANNED: authorization passed
    PLANNED --> FAILED: revalidation changed or send failed
    PLANNED --> SENT: exact input sent
    SENT --> VERIFIED: expected transition observed
    SENT --> FAILED: verification or retry budget failed
    VERIFIED --> [*]
    FAILED --> [*]
```

The state store prevents replay of unsettled action keys. Bounded Codex retries
use a persistent session/process/reset episode and a separately reserved action
key for each attempt, so a changed screen fingerprint cannot replenish budget.
Episode reservations and `PLANNED` are durable before the final recheck. That
recheck refreshes quota/prompt evidence, then directly rereads process identity
and classification immediately before `sendText`; no disk write intervenes.
Konsole offers no atomic compare-screen-and-send operation, so a residual
asynchronous boundary remains and must not be described as atomic.

Malformed retry state disables timed trials; pending `PLANNED` attempts are not
replayed after restart. A pending `SENT` can be verified without another send.
An episode that ended in a verified resume with nothing pending is dropped 24 h
after its reset, on load and at every rediscovery; an exhausted episode is kept,
because it is what stops the same process minting a fresh budget.
The event log records identifiers, pattern IDs, decisions,
and lifecycle states, but never screen contents, prompts, credentials, or
environment values.

## Deployment and trust boundaries

```mermaid
flowchart LR
    subgraph desktop["Desktop user account"]
        tui["Interactive CLI/TUI"]
        service["Optional systemd user service"]
        lock["Runtime single-instance lock"]
        files["Owner-only state, quota projection, and rotated log"]
        konsole["Konsole session D-Bus objects"]
    end
    internet["Public provider status endpoints"]

    tui --> lock
    service --> lock
    tui --> files
    service --> files
    tui --> konsole
    service --> konsole
    tui --> internet
    service --> internet
```

Only one input-capable process may hold the runtime lock. Observe-only processes
may coexist. The holder also serves a control socket beside the lock, so a
watcher started later can ask for the lock instead of being locked out for the
lifetime of a service: the holder releases before it answers and re-arms when
the successor exits, which keeps the single-writer guarantee that the lock, not
the protocol, enforces. D-Bus access, state files, and the service all remain
within the desktop user account; root execution, SSH, containers, tmux/screen,
and ambiguous process ancestry are non-automatable.

## Architectural decisions

- Keep provider quota state distinct from terminal prompt state.
- Bind selection to immutable process evidence, not a tab number or project path.
- Revalidate every safety input immediately before terminal input.
- Prefer refusal over inference; allow only the documented, explicitly opted-in
  bounded Codex trial when availability cannot refresh while blocked.
- Keep runtime dependencies empty and external traffic limited to compressed,
  bounded, conditional reads of public status endpoints.
- Persist the action intent before sending so crashes cannot silently duplicate
  an action.
- Route every operator-initiated input, such as the dashboard's whip crack,
  through the supervisor's revalidation; it types only into a plain working
  screen whose own composer is visibly empty, and is never persisted or retried.
- Preserve a narrow adapter boundary for future terminals or providers without
  weakening the current Konsole-specific gate.
