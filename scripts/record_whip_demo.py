#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Marcel Petrick
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Record the whip as an animated GIF: the crack, and where the reminder lands.

The upper half of every frame is the real dashboard from
:func:`agent_while_true.ui.render_status`, and the crack is the real ASCII
animation from :func:`agent_while_true.whip.frames`. The lower half shows three
of the supervised Konsole tabs, so the reminder can be seen arriving: two
working agents with empty composers receive it, and one with a half-typed draft
is skipped, exactly as the gate decides. Sessions, projects, accounts and the
agents' replies are invented, and every frame's caption says so.

Usage::

    python3 scripts/record_whip_demo.py media/agentWhileTrue_whip.gif
"""

from __future__ import annotations

import re
import sys
import tempfile
import textwrap
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from record_demo import COLUMNS, THEME, _assemble, _quota, _session, draw_frame

from agent_while_true import whip
from agent_while_true.config import Config, Mode, Policy
from agent_while_true.fsm import SupervisedSession
from agent_while_true.service_health import HealthState, ProviderHealth
from agent_while_true.states import SessionState
from agent_while_true.ui import _PALETTES, render_status
from agent_while_true.version import __version__

CAPTION = (
    f"scripted demo of the agent-while-true {__version__} whip - invented sessions and "
    "replies; the dashboard, the crack and the gate's decisions are the real code"
)
#: The phrases each crack types into the two receiving tabs: every session a
#: crack reaches gets its own reminder, so the Claude and Codex tabs differ.
FIRST = (1, 30)
LATER = (10, 34)

_RESET = "\x1b[0m"
_PANE = "\x1b[38;5;252;48;5;234m"
_PANE_BORDER = "\x1b[38;5;240;48;5;234m"
_PANE_TITLE = "\x1b[1;38;5;16;48;5;45m"
_PANE_DIM = "\x1b[38;5;244;48;5;234m"
_WHIP_TEXT = "\x1b[1;38;5;226;48;5;234m"
_CLAUDE = "\x1b[1;38;5;213;48;5;234m"
_CODEX = "\x1b[1;38;5;81;48;5;234m"
_OK = "\x1b[1;38;5;48;48;5;234m"
_SKIP = "\x1b[1;38;5;214;48;5;234m"
_LABEL = "\x1b[38;5;153;48;5;17m"
_FLASH = "\x1b[1;38;5;16;48;5;214m"
_LASH = "\x1b[1;38;5;231;48;5;17m"
_ART = "\x1b[1;38;5;208;48;5;17m"

#: The two composers' cursor glyphs, spelled out so they cannot be misread.
CLAUDE_CURSOR = "\N{HEAVY RIGHT-POINTING ANGLE QUOTATION MARK ORNAMENT}"
CODEX_CURSOR = "\N{SINGLE RIGHT-POINTING ANGLE QUOTATION MARK}"

PANE_WIDTH = (COLUMNS - 4) // 3
PANE_ROWS = 11
_ANSI = re.compile(r"\x1b\[[0-9;]*m")


def _visible(text: str) -> int:
    return len(_ANSI.sub("", text))


def pane(title: str, rows: list[tuple[str, str]], *, flash: bool = False) -> list[str]:
    """One framed terminal tab: a title bar and ``(style, text)`` rows."""
    inner = PANE_WIDTH - 4
    bar = f" {title}{'  >> WHIP! <<' if flash else ''} "[: PANE_WIDTH - 2]
    lines = [(_FLASH if flash else _PANE_TITLE) + bar.ljust(PANE_WIDTH) + _RESET]
    body: list[tuple[str, str]] = []
    for style, text in rows:
        wrapped = textwrap.wrap(text, inner, subsequent_indent="  ") or [""]
        body.extend((style, part) for part in wrapped)
    body = body[-(PANE_ROWS - 2) :]
    body += [(_PANE, "")] * (PANE_ROWS - 2 - len(body))
    for style, text in body:
        lines.append(f"{_PANE_BORDER}│ {style}{text.ljust(inner)}{_PANE_BORDER} │{_RESET}")
    lines.append(_PANE_BORDER + "└" + "─" * (PANE_WIDTH - 2) + "┘" + _RESET)
    return lines


def side_by_side(panes: list[list[str]]) -> list[str]:
    gap = _LABEL + "  " + _RESET
    return [gap.join(row) for row in zip(*panes, strict=True)]


def tabs(stage: str, *, flash: bool = False) -> list[str]:
    """The three Konsole tabs at one moment of the story."""
    phrases = LATER if stage == "later" else FIRST
    claude_text, codex_text = (whip.message(phrase) for phrase in phrases)
    claude_work = [
        (_PANE, "● Update(src/harbour/dock.py)"),
        (_PANE_DIM, "  └ Updated with 4 additions and 1 removal"),
        (_PANE, "● Bash(pytest -q tests/test_dock.py)"),
        (_PANE_DIM, "  └ 18 passed in 0.41s"),
        (_CLAUDE, "✻ Pondering the meaning of harbours… (esc to interrupt)"),
    ]
    codex_work = [
        (_PANE, "• Ran cargo test --workspace"),
        (_PANE_DIM, "  └ 142 passed; 0 failed"),
        (_PANE, "• Explored src/tides/mapper.rs"),
        (_CODEX, "• Working (4m 12s • esc to interrupt)"),
    ]
    draft = [
        (_PANE, "● The lantern renderer now batches glyph uploads."),
        (_PANE_DIM, "✻ Crunched for 2m 5s"),
        (_PANE, ""),
    ]
    claude_prompt = (_CLAUDE, f"{CLAUDE_CURSOR} ")
    codex_prompt = (_CODEX, f"{CODEX_CURSOR} Ask Codex to do anything")
    claude_foot = (_PANE_DIM, "  Opus 5 ctx:31% 5h:44% reset:3h40m")
    codex_foot = (_PANE_DIM, "  gpt-5-codex high · ~/code/tide-mapper · 38% used")
    draft_prompt = (_PANE, f"{CLAUDE_CURSOR} also rename the helper before you")
    draft_note: list[tuple[str, str]] = []

    if stage == "typed":
        claude_prompt = (_WHIP_TEXT, f"{CLAUDE_CURSOR} {claude_text}")
        codex_prompt = (_WHIP_TEXT, f"{CODEX_CURSOR} {codex_text}")
        draft_note = [(_SKIP, "  (whip skipped: your draft stays yours)")]
    elif stage == "answered":
        claude_work = [
            *claude_work[2:4],
            (_WHIP_TEXT, f"{CLAUDE_CURSOR} {claude_text}"),
            (_CLAUDE, "● On it. Shipping the dock refactor, no essay."),
        ]
        codex_work = [
            *codex_work[:2],
            (_WHIP_TEXT, f"{CODEX_CURSOR} {codex_text}"),
            (_CODEX, "• Understood. Finishing the mapper; tests next."),
        ]
        draft_note = [(_SKIP, "  (whip skipped: your draft stays yours)")]
    elif stage == "later":
        claude_work = [
            (_OK, "● Dock refactor done: 4 files, 23 tests green."),
            (_WHIP_TEXT, f"{CLAUDE_CURSOR} {claude_text}"),
            (_CLAUDE, "● Committing now."),
        ]
        codex_work = [
            (_OK, "• Mapper finished; cargo test 148 passed."),
            (_WHIP_TEXT, f"{CODEX_CURSOR} {codex_text}"),
            (_CODEX, "• Pushing the branch."),
        ]

    return side_by_side(
        [
            pane(
                "pts/9 · claude · ~/code/glass-harbour",
                [*claude_work, (_PANE, ""), claude_prompt, claude_foot],
                flash=flash,
            ),
            pane(
                "pts/5 · codex · ~/code/tide-mapper",
                [*codex_work, (_PANE, ""), codex_prompt, codex_foot],
                flash=flash,
            ),
            pane(
                "pts/11 · claude · ~/code/paper-lantern",
                [*draft, draft_prompt, *draft_note, claude_foot],
            ),
        ]
    )


def cast(now: datetime) -> list[SupervisedSession]:
    """Six invented sessions, all working."""
    session_reset = now + timedelta(hours=3, minutes=40)
    aurora, orbit = "aurora · pilot@example.invalid", "orbit · relay@example.invalid"
    harbour, ledger = "harbour · keeper@example.invalid", "ledger · scribe@example.invalid"
    rows = (
        ("codex", "pts/2", 30211, aurora, "~/code/lunar-atlas", 34, 41),
        ("codex", "pts/5", 30588, aurora, "~/code/tide-mapper", 38, 58),
        ("codex", "pts/7", 31040, orbit, "~/code/beacon-relay", 52, 47),
        ("claude", "pts/9", 31477, harbour, "~/code/glass-harbour", 44, 30),
        ("claude", "pts/11", 31902, harbour, "~/code/paper-lantern", 28, 22),
        ("claude", "pts/13", 32260, ledger, "~/code/quartz-ledger", 61, 35),
    )
    return [
        _session(
            tty=tty,
            pid=pid,
            provider=provider,
            account=account,
            title=title,
            state=SessionState.ACTIVE,
            observed_at=now,
            next_check=now + timedelta(seconds=2),
            reason="no-recognised-blocking-prompt:ACTIVE",
            quota=_quota(
                provider,
                session_used=used,
                week_used=week,
                now=now,
                session_reset=session_reset,
                week_reset=now + timedelta(days=3),
            ),
        )
        for provider, tty, pid, account, title, used, week in rows
    ]


def dashboard(now: datetime, badge: str, last_event: str, events: tuple[str, ...]) -> list[str]:
    health = {
        name: ProviderHealth(name, HealthState.ONLINE, "", now - timedelta(seconds=9))
        for name in ("openai", "anthropic")
    }
    return render_status(
        cast(now),
        now=now,
        config=Config(mode=Mode.AUTO, policy=Policy(allow_codex_auto_resume=True)),
        last_event=last_event,
        refresh_interval=2.0,
        color=True,
        theme=THEME,
        width=COLUMNS,
        events=events,
        show_events=True,
        history_length=4,
        service_health=health,
        whip_badge=badge,
    ).splitlines()


def paint_crack(frame: str, height: int) -> list[str]:
    """Colour one ASCII whip frame onto the dashboard's own surface."""
    handle_row = max(2, (height * 2) // 3)
    burst = is_burst(frame)
    painted = []
    for row, line in enumerate(frame.split("\n")):
        style = _ART if burst and row < handle_row - 1 else _LASH
        painted.append(style + line.ljust(COLUMNS) + _RESET)
    return painted


def is_burst(frame: str) -> bool:
    return "____" in frame or "CRACK" in frame


def storyboard(start: datetime) -> list[tuple[list[str], int]]:
    """``(screen lines, milliseconds)`` for every frame of the GIF."""
    label = _LABEL + "  other Konsole tabs, supervised by the watcher above".ljust(COLUMNS) + _RESET
    steps: list[tuple[list[str], list[str], int]] = []
    before = ("resume_verified codex pts/5 result=resumed",)
    claude_first, codex_first = FIRST
    delivered = (
        f"whip_delivered codex pts/5 phrase={codex_first}",
        f"whip_delivered claude pts/9 phrase={claude_first}",
        "whip_skipped claude pts/11 phrase=- reason=composer-not-empty",
        "whip_cracked delivered=5 sessions=6",
    )
    hint = "six agents working - press w to crack the whip"
    idle = dashboard(start, "whip=0 sent=0", hint, before)
    steps.append((idle, tabs("working"), 2600))

    height = len(idle)
    crack_frames = whip.frames(COLUMNS, height)
    for index, frame in enumerate(crack_frames):
        duration = 90 if index < len(crack_frames) - 3 else 260
        steps.append((paint_crack(frame, height), tabs("working", flash=is_burst(frame)), duration))

    moment = start + timedelta(seconds=2)
    reached = (
        "whip cracked: reached 5/6 with 5 different reminders, "
        f'e.g. "{whip.PHRASES[codex_first]}"; skipped 1x composer-not-empty'
    )
    after = dashboard(moment, "whip=1 sent=5", reached, delivered)
    steps.append((after, tabs("typed"), 2200))
    steps.append((after, tabs("answered"), 3200))

    later = start + timedelta(seconds=39)
    cooling = dashboard(
        later,
        "whip=5 sent=25 cooldown 21s",
        f"whip cooling down for 21s: {whip.CRACKS_PER_WINDOW} cracks a minute is the limit",
        (
            "whip_cracked delivered=5 sessions=6",
            f"whip_delivered claude pts/9 phrase={LATER[0]}",
            f"whip_delivered codex pts/5 phrase={LATER[1]}",
            "whip_cracked delivered=5 sessions=6",
        ),
    )
    steps.append((cooling, tabs("later"), 3600))

    tallest = max(len(top) for top, _, _ in steps)
    screens = []
    for top, bottom, duration in steps:
        padding = [_PALETTES[THEME]["surface"] + " " * COLUMNS + _RESET] * (tallest - len(top))
        screens.append(([*top, *padding, label, *bottom], duration))
    return screens


def main(argv: list[str]) -> int:
    destination = Path(argv[1]) if len(argv) > 1 else Path("media/agentWhileTrue_whip.gif")
    start = datetime(2026, 9, 24, 15, 30, tzinfo=UTC)
    with tempfile.TemporaryDirectory() as workspace:
        paths, durations = [], []
        size: tuple[int, int] | None = None
        for index, (lines, duration) in enumerate(storyboard(start)):
            path = Path(workspace) / f"frame_{index:03d}.png"
            size = draw_frame("\n".join(lines), path, size, caption=CAPTION)
            paths.append(path)
            durations.append(duration)
        destination.parent.mkdir(parents=True, exist_ok=True)
        _assemble(paths, durations, destination)
    print(f"{destination} ({destination.stat().st_size / 1024:.0f} KiB, {len(paths)} frames)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
