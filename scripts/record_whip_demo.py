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
    python3 scripts/record_whip_demo.py --linkedin media/agentWhileTrue_whip_linkedin.gif

``--linkedin`` renders at twice the resolution with two taller agent tabs and
the repository URL in the caption, and stays inside LinkedIn's limits for an
animated GIF in a post: under 5 MB and under 400 frames (uploaded through the
photo button; larger files are frozen on their first frame).
"""

from __future__ import annotations

import re
import sys
import tempfile
import textwrap
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from record_demo import COLUMNS, FONT_SIZE, THEME, _assemble, _quota, _session, draw_frame

from agent_while_true import whip
from agent_while_true.config import Config, Mode, Policy
from agent_while_true.fsm import SupervisedSession
from agent_while_true.service_health import HealthState, ProviderHealth
from agent_while_true.states import SessionState
from agent_while_true.ui import _PALETTES, paint_whip_frame, render_status
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

#: The two composers' cursor glyphs, spelled out so they cannot be misread.
CLAUDE_CURSOR = "\N{HEAVY RIGHT-POINTING ANGLE QUOTATION MARK ORNAMENT}"
CODEX_CURSOR = "\N{SINGLE RIGHT-POINTING ANGLE QUOTATION MARK}"


@dataclass(frozen=True, slots=True)
class Layout:
    """How the Konsole tabs under the dashboard are laid out, and how large."""

    pane_width: int
    pane_rows: int
    draft_tab: bool
    font_size: int
    caption: str


README = Layout(
    pane_width=(COLUMNS - 4) // 3,
    pane_rows=11,
    draft_tab=True,
    font_size=FONT_SIZE,
    caption=CAPTION,
)
LINKEDIN = Layout(
    pane_width=(COLUMNS - 2) // 2,
    pane_rows=13,
    draft_tab=False,
    font_size=FONT_SIZE * 2,
    caption=(
        "Agent While True - press w: one crack, a different pep talk in every agent tab. "
        "github.com/marcelpetrick/AgentWhileTrue  (scripted demo, invented sessions)"
    ),
)
_ANSI = re.compile(r"\x1b\[[0-9;]*m")


def _visible(text: str) -> int:
    return len(_ANSI.sub("", text))


def pane(
    title: str, rows: list[tuple[str, str]], layout: Layout, *, flash: bool = False
) -> list[str]:
    """One framed terminal tab: a title bar and ``(style, text)`` rows."""
    width, height = layout.pane_width, layout.pane_rows
    inner = width - 4
    bar = f" {title}{'  >> WHIP! <<' if flash else ''} "[: width - 2]
    lines = [(_FLASH if flash else _PANE_TITLE) + bar.ljust(width) + _RESET]
    body: list[tuple[str, str]] = []
    for style, text in rows:
        wrapped = textwrap.wrap(text, inner, subsequent_indent="  ") or [""]
        body.extend((style, part) for part in wrapped)
    body = body[-(height - 2) :]
    body += [(_PANE, "")] * (height - 2 - len(body))
    for style, text in body:
        lines.append(f"{_PANE_BORDER}│ {style}{text.ljust(inner)}{_PANE_BORDER} │{_RESET}")
    lines.append(_PANE_BORDER + "└" + "─" * (width - 2) + "┘" + _RESET)
    return lines


def side_by_side(panes: list[list[str]]) -> list[str]:
    gap = _LABEL + "  " + _RESET
    return [gap.join(row) for row in zip(*panes, strict=True)]


def tabs(stage: str, layout: Layout, *, flash: bool = False) -> list[str]:
    """The Konsole tabs at one moment of the story."""
    phrases = LATER if stage == "later" else FIRST
    claude_text, codex_text = (whip.message(phrase) for phrase in phrases)
    claude_work = [
        (_PANE, "● Read(src/harbour/dock.py)"),
        (_PANE_DIM, "  └ Read 212 lines"),
        (_PANE, "● Update(src/harbour/dock.py)"),
        (_PANE_DIM, "  └ Updated with 4 additions and 1 removal"),
        (_PANE, "● Bash(pytest -q tests/test_dock.py)"),
        (_PANE_DIM, "  └ 18 passed in 0.41s"),
        (_CLAUDE, "✻ Pondering the meaning of harbours… (esc to interrupt)"),
    ]
    codex_work = [
        (_PANE, "• Explored src/tides/"),
        (_PANE_DIM, "  └ Read mapper.rs, tides.rs, lib.rs"),
        (_PANE, "• Edited src/tides/mapper.rs (+38 -11)"),
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
    # Claude frames its input box with a rule above and below; the whip's gate
    # only trusts an empty cursor row that sits directly on the closing rule.
    claude_rule = (_PANE_BORDER, "\u2500" * (layout.pane_width - 4))
    codex_foot = (_PANE_DIM, "  gpt-5-codex high · ~/code/tide-mapper · 38% used")
    draft_prompt = (_PANE, f"{CLAUDE_CURSOR} also rename the helper before you")
    draft_note: list[tuple[str, str]] = []

    if stage == "typed":
        claude_prompt = (_WHIP_TEXT, f"{CLAUDE_CURSOR} {claude_text}")
        codex_prompt = (_WHIP_TEXT, f"{CODEX_CURSOR} {codex_text}")
        draft_note = [(_SKIP, "  (whip skipped: your draft stays yours)")]
    elif stage == "answered":
        claude_work = [
            *claude_work[:-1],
            (_WHIP_TEXT, f"{CLAUDE_CURSOR} {claude_text}"),
            (_CLAUDE, "● On it. Shipping the dock refactor, no essay."),
        ]
        codex_work = [
            *codex_work[:-2],
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

    panes = [
        pane(
            "pts/9 · claude · ~/code/glass-harbour",
            [*claude_work, claude_rule, claude_prompt, claude_rule, claude_foot],
            layout,
            flash=flash,
        ),
        pane(
            "pts/5 · codex · ~/code/tide-mapper",
            [*codex_work, (_PANE, ""), codex_prompt, codex_foot],
            layout,
            flash=flash,
        ),
    ]
    if layout.draft_tab:
        panes.append(
            pane(
                "pts/11 · claude · ~/code/paper-lantern",
                [*draft, claude_rule, draft_prompt, claude_rule, *draft_note, claude_foot],
                layout,
            )
        )
    return side_by_side(panes)


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


def is_burst(rows: list[list[tuple[str, str]]]) -> bool:
    """Whether a crack frame is one of the snap frames carrying the CRACK art."""
    return any(part == "art" for row in rows for _, part in row)


def storyboard(start: datetime, layout: Layout = README) -> list[tuple[list[str], int]]:
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
    steps.append((idle, tabs("working", layout), 2600))

    height = len(idle)
    # The dashboard's own painter, so the recording shows the crack exactly as
    # the running tool draws it in this theme.
    crack_frames = whip.frame_segments(COLUMNS, height)
    for index, rows in enumerate(crack_frames):
        duration = 90 if index < len(crack_frames) - 3 else 260
        painted = paint_whip_frame(rows, color=True, theme=THEME).split("\n")
        steps.append((painted, tabs("working", layout, flash=is_burst(rows)), duration))

    moment = start + timedelta(seconds=2)
    reached = (
        "whip cracked: reached 5/6 with 5 different reminders, "
        f'e.g. "{whip.PHRASES[codex_first]}"; skipped 1x composer-not-empty'
    )
    after = dashboard(moment, "whip=1 sent=5", reached, delivered)
    steps.append((after, tabs("typed", layout), 2200))
    steps.append((after, tabs("answered", layout), 3200))

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
    steps.append((cooling, tabs("later", layout), 3600))

    tallest = max(len(top) for top, _, _ in steps)
    screens = []
    for top, bottom, duration in steps:
        padding = [_PALETTES[THEME]["surface"] + " " * COLUMNS + _RESET] * (tallest - len(top))
        screens.append(([*top, *padding, label, *bottom], duration))
    return screens


def main(argv: list[str]) -> int:
    arguments = argv[1:]
    layout = LINKEDIN if "--linkedin" in arguments else README
    paths_given = [argument for argument in arguments if argument != "--linkedin"]
    destination = Path(paths_given[0]) if paths_given else Path("media/agentWhileTrue_whip.gif")
    start = datetime(2026, 9, 24, 15, 30, tzinfo=UTC)
    with tempfile.TemporaryDirectory() as workspace:
        paths, durations = [], []
        size: tuple[int, int] | None = None
        for index, (lines, duration) in enumerate(storyboard(start, layout)):
            path = Path(workspace) / f"frame_{index:03d}.png"
            size = draw_frame(
                "\n".join(lines), path, size, caption=layout.caption, font_size=layout.font_size
            )
            paths.append(path)
            durations.append(duration)
        destination.parent.mkdir(parents=True, exist_ok=True)
        _assemble(paths, durations, destination)
    width, height = size or (0, 0)
    print(
        f"{destination} ({destination.stat().st_size / 1024:.0f} KiB, {len(paths)} frames, "
        f"{width}x{height}, {sum(durations) / 1000:.1f} s)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
