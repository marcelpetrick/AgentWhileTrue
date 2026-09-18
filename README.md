<!--
SPDX-FileCopyrightText: 2026 Marcel Petrick

SPDX-License-Identifier: GPL-3.0-or-later
-->

# Agent While True

[![Quality](https://github.com/marcelpetrick/AgentWhileTrue/actions/workflows/quality.yml/badge.svg?branch=master)](https://github.com/marcelpetrick/AgentWhileTrue/actions/workflows/quality.yml)
[![Release](https://github.com/marcelpetrick/AgentWhileTrue/actions/workflows/release.yml/badge.svg)](https://github.com/marcelpetrick/AgentWhileTrue/actions/workflows/release.yml)
[![Python 3.12+](https://img.shields.io/badge/Python-3.12%2B-3776AB.svg)](https://www.python.org/)
[![License: GPL v3 or later](https://img.shields.io/badge/license-GPLv3%2B-blue.svg)](LICENSE)

**Agent While True** is a dashboard and babysitter for Codex CLI and Claude
Code sessions running in KDE Konsole. One terminal shows every selected agent's
state, account, five-hour and weekly quota, and reset countdown. When a session
stops on a usage limit, Agent While True can wait for the window to reopen and
resume that session for you.

It is built to refuse rather than guess: only sessions you selected, only exact
tested prompts, only after fresh provider evidence, and never a paid, upgrade,
reset-credit or model-downgrade choice. Start in observe mode, read why a
session is waiting, and switch automation on when you trust it.

![Agent While True auto-mode dashboard](media/agentWhileTrue_v0.33.0.png)

## What it does

- **One view across your agents** — selected Codex and Claude sessions, their
  accounts, usage meters, prompt and quota reset times, and public provider
  service health.
- **Resume with guardrails** — observe without typing, confirm each action, or
  let it continue exact tested prompts automatically; Codex composer input and
  Claude's own "wait, then continue" menu are separate, explicit opt-ins.
- **Explanations, not surprises** — a detail panel shows the latest decision,
  quota freshness, blocking windows and the next scheduled check.
- **A record of what happened** — persisted `PLANNED → SENT → VERIFIED|FAILED`
  history and day/week summaries, holding identifiers and pattern IDs only,
  never terminal text.

Target platform: Manjaro/Arch Linux, KDE Plasma, Konsole (Wayland or X11),
Python 3.12+, `qdbus6`. The runtime has no third-party dependencies.

## Install

```bash
pipx install 'git+https://github.com/marcelpetrick/AgentWhileTrue.git@agentwhiletrue-v0.45.6'
agent-while-true --version
agent-while-true doctor
```

`pipx` isolates the CLI and leaves it on `PATH` as `~/.local/bin/agent-while-true`.
Pick any tag from the [releases](https://github.com/marcelpetrick/AgentWhileTrue/releases);
a development checkout is described in [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md).

## Quick start

```bash
agent-while-true doctor              # is this environment supported? can auto mode work?
agent-while-true status              # which Konsole sessions are agents, and why not?
agent-while-true quota               # what do the providers say about usage and resets?
agent-while-true run --observe --all # watch everything; never type
```

Ask and auto mode need Konsole's input D-Bus API enabled once
(`EnableSecuritySensitiveDBusAPI`) and Konsole restarted — see
[docs/USAGE.md §1](docs/USAGE.md#1-enable-konsole-input-once). In the running
dashboard, `Shift+A` switches between observe and full-auto, `d` explains the
selected session, `h` lists every key.

| Mode | Command | Sends input? |
| --- | --- | --- |
| Observe | `run --observe` | Never. Runs the complete detection path and reports what it would do. |
| Ask | `run --ask` | Only after you confirm each action. |
| Auto | `run --auto` | Yes, for policy-approved exact prompts, after fresh revalidation. |

A background observe-only user service, the Claude quota bridge, configuration
keys, Codex timed retries and the full dashboard reference are all in
[docs/USAGE.md](docs/USAGE.md).

## Safety in brief

Immediately before any input, Agent While True re-reads and verifies the
selected Konsole session; the PID, process start time, TTY and provider
classification; a current known prompt and its permitted action; fresh provider
quota (or the narrowly opted-in Codex timed-trial gate); and the persisted
prompt fingerprint and retry budget. SSH, containers, tmux/screen, unknown
prompts, contradictory quota, process replacement and every paid or
quality-changing choice fail closed. A single-instance lock and the persisted
action lifecycle prevent duplicate input across processes and crashes.

Unknown or stale quota never means available. The reasoning is in
[docs/vision.md](docs/vision.md); the implemented gates are in
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Documentation

| Document | Read it for |
| --- | --- |
| [docs/USAGE.md](docs/USAGE.md) | Operating the tool: Konsole setup, modes, dashboard keys, configuration, logs, Codex and Claude specifics, the quota bridge, the systemd service |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Components, data flow, the guarded resume flow and the persisted action lifecycle |
| [docs/vision.md](docs/vision.md) | Product intent and the safety invariants (DANGER 1–20) every change must preserve |
| [docs/PLAN.md](docs/PLAN.md) | What is implemented, the remaining acceptance gate, and the maintenance plan |
| [docs/OPEN_ISSUES.md](docs/OPEN_ISSUES.md) | The single authoritative list of open acceptance and maintenance work |
| [docs/PERFORMANCE.md](docs/PERFORMANCE.md) | Measured workload, network traffic and profiling evidence |
| [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) | The quality gate, CI workflows, SBOMs, versioning and release artifacts |
| [AGENTS.md](AGENTS.md) | Contributor rules: commit style, required verification, release procedure |
| [CHANGELOG.md](CHANGELOG.md) | Every release, newest first |

## Project

Author: Marcel Petrick <mail@marcelpetrick.it>. Licensed under the
[GNU General Public License v3.0 or later](LICENSE); the package metadata
declares `GPL-3.0-or-later` and built distributions include the license.
The project is generated with AI.
