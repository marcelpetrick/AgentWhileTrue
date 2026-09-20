<!--
SPDX-FileCopyrightText: 2026 Marcel Petrick

SPDX-License-Identifier: GPL-3.0-or-later
-->

# LinkedIn post material — Agent While True

Collected source material for a short LinkedIn post (planned: 2026-09-21).
This is **not** the finished post. It is the raw pile: the story in my own
words, the ten bullets, the technical findings behind them, the hard numbers,
and the link.

Repository: <https://github.com/marcelpetrick/AgentWhileTrue>

Source notes in this repository: [../vision.md](../vision.md) (DANGER 1–20),
[../ARCHITECTURE.md](../ARCHITECTURE.md), [../../CHANGELOG.md](../../CHANGELOG.md).

---

## 1. The storyline (the hook)

Imagine you are doing a barbecue with your friends — but you also have a heavy
agentic task running. You do not want to invest in a high-token account or an
expensive subscription per month, so of course you run into the five-hour
window or the weekly window. And you are busy with your friends and not
listening to the terminal.

How do you make sure the task gets continued by Codex CLI or Claude Code even
when you are not there?

Two weeks ago, when I started with this, it seemed like a really simple task:
just do some overwatch, see if a terminal is showing one of those messages, and
continue from there after the window has reset.

It turned out the task itself is a bit harder.

---

## 2. In my own words (use more or less verbatim)

> In the beginning, two weeks ago when I started with that, it seemed like a
> really simple task: just do some overwatch, check if some kind of terminal is
> showing one of those messages, and then continue from there after the window
> has reset. But it turned out that the task itself is a bit harder.
>
> First you have to recover the state. When you work on a proper Linux desktop,
> you also have several shells of security which prevent direct access or
> copy-pasting — so we are using D-Bus here. Then: how the terminals work. Then,
> over the last 14 days, the behaviour of how the harnesses report that you have
> run out of tokens also varied. And of course I wanted to prevent that I
> accidentally upgrade my account and pay more, or do other things.
>
> All those corner cases, which were not considered in the initial prototype, I
> figured out over time. I also created tests for them, and of course they are
> covered now. But the thing is: it is a real-world task. And since I also can't
> manipulate the root cause — except that I can use up all the budget and then
> see if the next run is working — it also took some time to get it implemented.
>
> So this is also one of those examples: just because you have AI, and you also
> have some software development skills, and both together — that doesn't mean
> that you get instantly a solution which is working out of the box. Because
> when you're operating in the unknown, then it's also a challenge to get the
> things right, even on the best assumptions. And of course I had time pressure,
> or so; I just wanted to get it done.
>
> And now I have a thing which can also work at night, or when I'm busy with
> something else — it can continue those tasks properly, and also in a safe
> environment. For instance, when you just want to do a dry run, you can put it
> into observe mode instead of full-auto mode.

Key takeaway sentence to keep: **AI plus software development skills does not
equal an instant working solution when you are operating in the unknown.**

Second takeaway: **the feedback loop itself was the bottleneck** — the only way
to test the real thing was to burn the whole budget and wait for the next
window.

---

## 3. The ten bullets

1. **You cannot just read another program's terminal on a modern Linux
   desktop.** Wayland and KDE put real walls between windows — no screen
   scraping, no clipboard tricks. The only sane path is Konsole's D-Bus API
   (`qdbus6`), and its input side is *disabled by default*, for a good reason.
2. **A terminal is not a text file.** It is a live, redrawing screen:
   scrollback, spinners, wrapped banners, ANSI noise. "Does this text appear?"
   is the wrong question; "what is on screen *right now*" is the right one.
3. **The harnesses keep changing the words.** Codex CLI 0.155.1 started writing
   `You’ve hit your usage limit` with a typographic apostrophe (U+2019) where
   0.154 used ASCII. One character. Two sessions sat blocked overnight. Every
   comparison now folds curly quotes, apostrophes and non-breaking spaces, and
   `doctor` warns when an installed provider CLI is newer than the prompt
   patterns it was verified against.
4. **Quota state and terminal prompt state are two different things.** The
   provider saying "reset at 19:40" and a session actually waiting for input are
   independent facts. Conflating them is how you type into a session that never
   asked for anything.
5. **A reset timestamp is not permission.** Unknown, missing, stale or malformed
   quota never means "available". Fail closed — the clock is a hint, not
   evidence.
6. **The most dangerous bug would be the helpful one.** An automation that
   "solves" a limit by accepting an upgrade, buying credits, spending reset
   credits, or silently downgrading the model. Those choices are hard-vetoed.
   The tool is never allowed to spend my money or quietly lower quality.
7. **"The same session" is surprisingly hard.** PIDs get reused, agents exit
   back to zsh, processes get replaced. A selection is bound to the Konsole
   service and session plus PID, process start time and TTY — and all of it is
   re-read immediately before a single character is sent.
8. **Fail closed on anything unusual.** SSH, containers, tmux/screen,
   contradictory classification signals, unknown prompts: all non-automatable by
   design. 20 documented danger cases, each with tests.
9. **Privacy is a feature, not a promise.** No terminal contents, no prompt
   text, no environment values, no credentials in the logs — only identifiers
   and pattern IDs. (And the log stays owner-only *across rotation* — that one
   was a real bug, found and fixed.)
10. **So it became a dashboard first and a babysitter second.** One terminal
    shows every selected agent, its account, five-hour and weekly usage and the
    reset countdown. Three modes: observe (never types), ask (confirm every
    action), auto (only exact tested prompts, after fresh revalidation). Correct
    refusal beats eager automation.

---

## 4. Technical findings worth mentioning (my notes from the code)

- **Transport:** KDE Konsole's D-Bus interface. Reading session content is one
  API; sending input is a separate, security-sensitive one
  (`EnableSecuritySensitiveDBusAPI`) that the user has to enable once and
  restart Konsole for. That switch is the whole reason this is possible at all
  on Wayland — and the reason it is honest about being an intentional decision.
- **Recognition is a versioned pattern table, not a regex someone wrote once.**
  Each provider adapter records which CLI versions its patterns were verified
  against (e.g. `codex-0.155.x`), so drift becomes a visible warning in
  `doctor`, not a silent "no action proposed".
- **Every real bug from a live prompt became a fixture first, then a fix.**
  Screenshots in `media/` are evidence; they get transcribed into deterministic
  fake-terminal tests. That is what makes a 5-hour-window bug reproducible in
  milliseconds instead of once per reset.
- **Persisted action lifecycle:** `PLANNED → SENT → VERIFIED | FAILED`, plus a
  single-instance lock. This survives crashes and prevents duplicate input from
  two processes — the classic "it pressed Enter twice" failure.
- **Revalidation is the core idea.** Identity, process class, visible prompt and
  policy are all re-read *directly before* `sendText`, not at decision time. The
  gap between "I decided" and "I typed" is where all the interesting bugs live.
- **The one timed exception is narrow and opt-in.** Codex continuation after an
  anchored reset, with a bounded persistent retry schedule, no contradictory
  quota, and full revalidation. Claude and everything else still need provider
  confirmation.
- **Claude's "wait, then continue" menu** is only selected for the exact tested
  menu, with the cursor visibly on item 1, a safe item 2, fresh exhausted quota
  and an explicit config flag. Every variation fails closed.
- **Zero runtime dependencies.** Python 3.12+ standard library only, on purpose:
  a supervisor with the right to type into your terminal should have the
  smallest possible supply chain.
- **Testing what you cannot trigger on demand.** You cannot ask a provider to
  reset your window. So: deterministic fake-terminal tests for everything
  reproducible, real screenshots for everything else, and a live opt-in test
  marker for the KDE-specific parts.

---

## 5. Hard numbers (all checkable in the repo)

| Fact | Value |
| --- | --- |
| Time from first commit to now | ~14 days |
| Current version | 0.49.0 |
| Documented danger cases | 20 (`docs/vision.md`, DANGER 1–20) |
| Production code | ~9,100 lines of Python |
| Test code | ~7,830 lines of Python |
| Runtime dependencies | 0 |
| Python | 3.12 / 3.13 / 3.14 |
| Coverage gate | ≥ 91 % |
| Platform | Manjaro/Arch, KDE Plasma, Konsole (Wayland or X11) |
| Supported agents | OpenAI Codex CLI, Anthropic Claude Code |
| License | GPL-3.0-or-later, REUSE compliant, SBOM per release |

---

## 6. Closing lines / CTA options

- "Correct refusal beats eager automation. The barbecue was great."
- "It now works at night, or while I'm busy with something else — and if you
  don't trust it yet, observe mode never types a single character."
- "Open source, GPLv3, zero runtime dependencies. Linux + KDE Konsole only —
  feedback and fixture contributions welcome."

Link: <https://github.com/marcelpetrick/AgentWhileTrue>

Possible tags: `#Linux` `#KDE` `#Python` `#AIAgents` `#ClaudeCode` `#CodexCLI`
`#DeveloperTools` `#OpenSource` `#Automation` `#SoftwareEngineering`
