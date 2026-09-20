#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Marcel Petrick
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Record the dashboard as an animated GIF, from invented sessions.

The frames come out of the real :func:`agent_while_true.ui.render_status`, so
the chrome, colours, meters and columns are the ones the tool actually draws.
Everything *in* them is fiction: invented projects, invented accounts, invented
process ids, and a storyboard that walks a limit from first warning through the
reset to a verified resume. Recording that against live sessions would publish a
developer's real project names, real account addresses and real usage, and would
also mean waiting hours for a genuine reset to arrive on cue.

Every frame carries a caption saying so, because a screenshot that looks like
evidence should say when it is not.

Usage::

    python3 scripts/record_demo.py media/agentWhileTrue_demo.gif
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from PIL import Image, ImageDraw, ImageFont

from agent_while_true.config import Config, Mode, Policy
from agent_while_true.fsm import SupervisedSession
from agent_while_true.proc import ProcessIdentity
from agent_while_true.quota import (
    Availability,
    QuotaSnapshot,
    QuotaWindow,
)
from agent_while_true.service_health import HealthState, ProviderHealth
from agent_while_true.states import SessionState
from agent_while_true.terminal.base import SessionRef
from agent_while_true.ui import render_status
from agent_while_true.version import __version__

#: The table layout needs 168 columns; below that the dashboard stacks each
#: session into a card, which is correct but reads poorly in a recording.
COLUMNS = 178
THEME = "vivid"
CAPTION = (
    f"scripted demo of agent-while-true {__version__} - invented sessions, "
    "accounts and timings; the dashboard itself is the real renderer"
)

#: Monospace faces, in the order they are tried.
FONT_CANDIDATES = (
    ("/usr/share/fonts/TTF/DejaVuSansMono.ttf", "/usr/share/fonts/TTF/DejaVuSansMono-Bold.ttf"),
    (
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf",
    ),
    (
        "/usr/share/fonts/noto/NotoSansMono-Regular.ttf",
        "/usr/share/fonts/noto/NotoSansMono-Bold.ttf",
    ),
)
FONT_SIZE = 13

_SGR = re.compile(r"\x1b\[([0-9;]*)m")

#: xterm's first sixteen colours; the palettes above 15 are computed.
_BASE16 = (
    (0x00, 0x00, 0x00), (0xCD, 0x00, 0x00), (0x00, 0xCD, 0x00), (0xCD, 0xCD, 0x00),
    (0x00, 0x00, 0xEE), (0xCD, 0x00, 0xCD), (0x00, 0xCD, 0xCD), (0xE5, 0xE5, 0xE5),
    (0x7F, 0x7F, 0x7F), (0xFF, 0x00, 0x00), (0x00, 0xFF, 0x00), (0xFF, 0xFF, 0x00),
    (0x5C, 0x5C, 0xFF), (0xFF, 0x00, 0xFF), (0x00, 0xFF, 0xFF), (0xFF, 0xFF, 0xFF),
)  # fmt: skip


def xterm_rgb(index: int) -> tuple[int, int, int]:
    """The RGB of one xterm-256 colour index."""
    if index < 16:
        return _BASE16[index]
    if index < 232:
        index -= 16
        levels = (0, 95, 135, 175, 215, 255)
        return levels[index // 36], levels[(index // 6) % 6], levels[index % 6]
    grey = 8 + (index - 232) * 10
    return grey, grey, grey


@dataclass(slots=True)
class Cell:
    """One character with the colours the renderer asked for."""

    char: str
    foreground: tuple[int, int, int]
    background: tuple[int, int, int]
    bold: bool


def parse_ansi(frame: str, default_bg: tuple[int, int, int]) -> list[list[Cell]]:
    """Turn a rendered frame into a grid of coloured cells.

    Only the sequences the palettes actually emit are handled: reset, bold, and
    256-colour foreground and background.
    """
    rows: list[list[Cell]] = []
    foreground = (0xD0, 0xD0, 0xD0)
    background = default_bg
    bold = False
    for line in frame.splitlines():
        row: list[Cell] = []
        position = 0
        for match in _SGR.finditer(line):
            for char in line[position : match.start()]:
                row.append(Cell(char, foreground, background, bold))
            position = match.end()
            codes = [int(part or 0) for part in match.group(1).split(";")]
            index = 0
            while index < len(codes):
                code = codes[index]
                if code == 0:
                    foreground, background, bold = (0xD0, 0xD0, 0xD0), default_bg, False
                elif code == 1:
                    bold = True
                elif code == 38 and codes[index + 1 : index + 2] == [5]:
                    foreground = xterm_rgb(codes[index + 2])
                    index += 2
                elif code == 48 and codes[index + 1 : index + 2] == [5]:
                    background = xterm_rgb(codes[index + 2])
                    index += 2
                elif 30 <= code <= 37:
                    foreground = _BASE16[code - 30]
                elif 40 <= code <= 47:
                    background = _BASE16[code - 40]
                index += 1
        for char in line[position:]:
            row.append(Cell(char, foreground, background, bold))
        rows.append(row)
    return rows


def _fonts() -> tuple[ImageFont.FreeTypeFont, ImageFont.FreeTypeFont]:
    for regular, bold in FONT_CANDIDATES:
        if Path(regular).exists():
            bold_path = bold if Path(bold).exists() else regular
            return (
                ImageFont.truetype(regular, FONT_SIZE),
                ImageFont.truetype(bold_path, FONT_SIZE),
            )
    raise SystemExit("no monospace font found; install DejaVu Sans Mono or Noto Sans Mono")


def draw_frame(frame: str, path: Path, size: tuple[int, int] | None = None) -> tuple[int, int]:
    """Rasterise one rendered frame, captioned, to a PNG."""
    regular, bold_font = _fonts()
    cell_width = round(regular.getlength("M"))
    cell_height = FONT_SIZE + 5
    background = (10, 10, 30)
    grid = parse_ansi(frame, background)

    margin = 12
    caption_height = cell_height + 22
    width = size[0] if size else margin * 2 + cell_width * COLUMNS
    height = size[1] if size else margin * 2 + cell_height * len(grid) + caption_height

    image = Image.new("RGB", (width, height), background)
    canvas = ImageDraw.Draw(image)
    for row_index, row in enumerate(grid):
        top = margin + row_index * cell_height
        for column_index, cell in enumerate(row):
            left = margin + column_index * cell_width
            canvas.rectangle(
                (left, top, left + cell_width - 1, top + cell_height - 1), fill=cell.background
            )
            if cell.char != " ":
                canvas.text(
                    (left, top + 2),
                    cell.char,
                    font=bold_font if cell.bold else regular,
                    fill=cell.foreground,
                )
    canvas.text(
        (margin, height - caption_height + 12),
        CAPTION,
        font=regular,
        fill=(150, 150, 180),
    )
    image.save(path)
    return width, height


def _quota(
    provider: str,
    *,
    session_used: float,
    week_used: float,
    now: datetime,
    session_reset: datetime,
    week_reset: datetime,
    availability: Availability = Availability.AVAILABLE,
    source: str = "",
    observed: datetime | None = None,
) -> QuotaSnapshot:
    return QuotaSnapshot(
        provider=provider,
        availability=availability,
        source=source or ("codex-rollout" if provider == "codex" else "claude-statusline"),
        observed_at=observed or now,
        windows=(
            QuotaWindow("session", session_used, session_reset),
            QuotaWindow("weekly", week_used, week_reset),
        ),
    )


def _session(
    *,
    tty: str,
    pid: int,
    provider: str,
    account: str,
    title: str,
    state: SessionState,
    quota: QuotaSnapshot,
    reset_at: datetime | None = None,
    reason: str = "",
    next_check: datetime | None = None,
    observed_at: datetime | None = None,
    observed_state: str = "",
    matched_ids: tuple[str, ...] = (),
) -> SupervisedSession:
    return SupervisedSession(
        ref=SessionRef(
            adapter="konsole", service=f"org.kde.konsole-{pid}", session_id="/Sessions/1"
        ),
        identity=ProcessIdentity(pid=pid, start_time=pid * 7, tty=tty, exe=f"/usr/bin/{provider}"),
        provider_name=provider,
        title=title,
        account_label=account,
        state=state,
        reset_at=reset_at,
        next_check_at=next_check,
        last_reason=reason,
        observed_state=observed_state or state.value,
        observed_at=observed_at,
        decision_at=observed_at,
        matched_ids=matched_ids,
        quota=quota,
    )


def storyboard(start: datetime) -> list[dict]:
    """A limit arriving, being waited out, and being resumed, in fourteen frames."""
    codex_week = start + timedelta(days=4, hours=3)
    claude_week = start + timedelta(days=2, hours=9)
    cast = {
        "atlas": ("codex", "pts/2", 30211, "aurora · pilot@example.invalid", "~/code/lunar-atlas"),
        "tide": ("codex", "pts/5", 30588, "aurora · pilot@example.invalid", "~/code/tide-mapper"),
        "beacon": ("codex", "pts/7", 31040, "orbit · relay@example.invalid", "~/code/beacon-relay"),
        "harbour": (
            "claude",
            "pts/9",
            31477,
            "harbour · keeper@example.invalid",
            "~/code/glass-harbour",
        ),
        "lantern": (
            "claude",
            "pts/11",
            31902,
            "harbour · keeper@example.invalid",
            "~/code/paper-lantern",
        ),
        "quartz": (
            "claude",
            "pts/13",
            32260,
            "ledger · scribe@example.invalid",
            "~/code/quartz-ledger",
        ),
    }

    def build(
        key: str,
        now: datetime,
        state: SessionState,
        session_used: float,
        week_used: float,
        *,
        session_reset: datetime,
        reset_at: datetime | None = None,
        reason: str = "",
        availability: Availability = Availability.AVAILABLE,
        observed: datetime | None = None,
        matched_ids: tuple[str, ...] = (),
    ) -> SupervisedSession:
        provider, tty, pid, account, title = cast[key]
        return _session(
            tty=tty,
            pid=pid,
            provider=provider,
            account=account,
            title=title,
            state=state,
            reset_at=reset_at,
            reason=reason,
            next_check=now + timedelta(seconds=2),
            observed_at=now,
            matched_ids=matched_ids,
            quota=_quota(
                provider,
                session_used=session_used,
                week_used=week_used,
                now=now,
                session_reset=session_reset,
                week_reset=codex_week if provider == "codex" else claude_week,
                availability=availability,
                observed=observed,
            ),
        )

    tide_reset = start + timedelta(minutes=12)
    harbour_reset = start + timedelta(minutes=15)
    steps: list[dict] = []

    def frame(
        minutes: float,
        sessions: list[SupervisedSession],
        last_event: str,
        events: tuple[str, ...] = (),
        *,
        details: bool = False,
        detail_index: int = 1,
        duration: int = 1700,
    ) -> None:
        steps.append(
            {
                "now": start + timedelta(minutes=minutes),
                "sessions": sessions,
                "last_event": last_event,
                "events": events,
                "details": True,
                "detail_index": detail_index,
                "duration": duration,
            }
        )

    def cohort(
        now: datetime,
        *,
        tide: tuple,
        harbour: tuple,
    ) -> list[SupervisedSession]:
        """The four steady sessions, plus the two the story moves."""
        session_reset = start + timedelta(hours=3, minutes=40)
        return [
            build("atlas", now, SessionState.ACTIVE, 34.0, 41.0, session_reset=session_reset),
            build("tide", now, *tide[:3], **tide[3]),
            build("beacon", now, SessionState.ACTIVE, 52.0, 47.0, session_reset=session_reset),
            build("harbour", now, *harbour[:3], **harbour[3]),
            build("lantern", now, SessionState.ACTIVE, 28.0, 22.0, session_reset=session_reset),
            build("quartz", now, SessionState.ACTIVE, 61.0, 35.0, session_reset=session_reset),
        ]

    steady = {"session_reset": tide_reset}
    calm_harbour = (SessionState.ACTIVE, 44.0, 30.0, {"session_reset": harbour_reset})

    now = start
    frame(
        0,
        cohort(now, tide=(SessionState.ACTIVE, 71.0, 58.0, steady), harbour=calm_harbour),
        "watching 6 sessions across 2 accounts",
        ("state_change codex pts/5 DISCOVERED -> ACTIVE",),
    )
    now = start + timedelta(minutes=2)
    frame(
        2,
        cohort(
            now,
            tide=(SessionState.LIMIT_WARNING, 93.0, 61.0, steady),
            harbour=calm_harbour,
        ),
        "codex pts/5 approaching its five-hour limit",
        ("state_change codex pts/5 ACTIVE -> LIMIT_WARNING",),
    )
    now = start + timedelta(minutes=4)
    blocked_tide = (
        SessionState.WAITING_FOR_RESET,
        100.0,
        62.0,
        {
            "session_reset": tide_reset,
            "reset_at": tide_reset,
            "reason": "usage-window-exhausted:session",
            "availability": Availability.EXHAUSTED,
            "matched_ids": ("codex/limit-usage", "codex/try-again-at"),
        },
    )
    frame(
        4,
        cohort(now, tide=blocked_tide, harbour=calm_harbour),
        "codex pts/5 blocked; waiting for the window, not typing",
        (
            "state_change codex pts/5 LIMIT_WARNING -> WAITING_FOR_RESET",
            "resume_refused codex pts/5 reason=usage-window-exhausted:session",
        ),
        duration=2300,
    )
    now = start + timedelta(minutes=6)
    blocked_harbour = (
        SessionState.LIMIT_BLOCKED,
        100.0,
        48.0,
        {
            "session_reset": harbour_reset,
            "reset_at": harbour_reset,
            "reason": "usage-not-confirmed-available",
            "availability": Availability.EXHAUSTED,
            "matched_ids": ("claude/limit-session",),
        },
    )
    frame(
        6,
        cohort(now, tide=blocked_tide, harbour=blocked_harbour),
        "claude pts/9 blocked too; both windows tracked separately",
        (
            "state_change claude pts/9 ACTIVE -> LIMIT_BLOCKED",
            "resume_refused claude pts/9 reason=usage-not-confirmed-available",
        ),
        detail_index=3,
    )
    frame(
        8,
        cohort(start + timedelta(minutes=8), tide=blocked_tide, harbour=blocked_harbour),
        "d opens the detail panel: why this session is waiting",
        ("detail codex pts/5 quota=EXHAUSTED source=codex-rollout",),
        details=True,
        duration=3200,
    )
    now = start + timedelta(minutes=12, seconds=30)
    ready_tide = (
        SessionState.READY_TO_RESUME,
        0.0,
        62.0,
        {
            "session_reset": start + timedelta(hours=5),
            "reset_at": tide_reset,
            "reason": "reset-confirmed-by-provider",
            "matched_ids": ("codex/limit-usage", "codex/try-again-at"),
        },
    )
    frame(
        12.5,
        cohort(now, tide=ready_tide, harbour=blocked_harbour),
        "codex pts/5 window reopened and the provider confirms it",
        ("state_change codex pts/5 WAITING_FOR_RESET -> READY_TO_RESUME",),
        duration=2100,
    )
    now = start + timedelta(minutes=13)
    sent_tide = (
        SessionState.CONTINUE_SENT,
        0.0,
        62.0,
        {
            "session_reset": start + timedelta(hours=5),
            "reset_at": tide_reset,
            "reason": "resume_sent action=TEXT_THEN_ENTER",
            "matched_ids": ("codex/limit-usage", "codex/try-again-at"),
        },
    )
    frame(
        13,
        cohort(now, tide=sent_tide, harbour=blocked_harbour),
        "continue sent to codex pts/5, awaiting verification",
        ("resume_sent codex pts/5 action=TEXT_THEN_ENTER authorization=PROVIDER_CONFIRMED",),
    )
    now = start + timedelta(minutes=13, seconds=20)
    frame(
        13.4,
        cohort(
            now,
            tide=(
                SessionState.VERIFYING,
                0.0,
                62.0,
                {
                    "session_reset": start + timedelta(hours=5),
                    "reset_at": tide_reset,
                    "reason": "verifying the session actually moved",
                },
            ),
            harbour=blocked_harbour,
        ),
        "verifying that the session actually resumed",
        ("state_change codex pts/5 CONTINUE_SENT -> VERIFYING",),
    )
    now = start + timedelta(minutes=14)
    resumed_tide = (
        SessionState.ACTIVE,
        4.0,
        62.0,
        {"session_reset": start + timedelta(hours=5)},
    )
    frame(
        14,
        cohort(now, tide=resumed_tide, harbour=blocked_harbour),
        "codex pts/5 resumed and verified",
        ("resume_verified codex pts/5 result=resumed",),
        duration=2300,
    )
    now = start + timedelta(minutes=15, seconds=40)
    frame(
        15.7,
        cohort(
            now,
            tide=resumed_tide,
            harbour=(
                SessionState.ACTIVE,
                3.0,
                48.0,
                {"session_reset": start + timedelta(hours=5, minutes=15)},
            ),
        ),
        "claude pts/9 resumed as well; all six running again",
        (
            "resume_verified claude pts/9 result=resumed",
            "resume_verified codex pts/5 result=resumed",
        ),
        detail_index=3,
        duration=2600,
    )
    return steps


def main(argv: list[str]) -> int:
    destination = Path(argv[1]) if len(argv) > 1 else Path("media/agentWhileTrue_demo.gif")
    start = datetime(2026, 9, 20, 14, 5, tzinfo=UTC)
    config = Config(mode=Mode.AUTO, policy=Policy(allow_codex_auto_resume=True))

    frames: list[str] = []
    durations: list[int] = []
    for step in storyboard(start):
        checked = step["now"] - timedelta(seconds=9)
        health = {
            name: ProviderHealth(name, HealthState.ONLINE, "", checked)
            for name in ("openai", "anthropic")
        }
        frames.append(
            render_status(
                step["sessions"],
                now=step["now"],
                config=config,
                last_event=step["last_event"],
                refresh_interval=2.0,
                color=True,
                theme=THEME,
                width=COLUMNS,
                events=step["events"],
                show_events=True,
                history_length=4,
                show_details=step["details"],
                detail_index=step["detail_index"],
                service_health=health,
            )
        )
        durations.append(step["duration"])

    # Every frame must be the same size, and the detail panel makes some taller.
    tallest = max(frame.count("\n") + 1 for frame in frames)
    frames = [frame + "\n" * (tallest - frame.count("\n") - 1) for frame in frames]

    with tempfile.TemporaryDirectory() as workspace:
        paths = []
        size: tuple[int, int] | None = None
        for index, frame in enumerate(frames):
            path = Path(workspace) / f"frame_{index:03d}.png"
            size = draw_frame(frame, path, size)
            paths.append(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        _assemble(paths, durations, destination)

    print(f"{destination} ({destination.stat().st_size / 1024:.0f} KiB, {len(frames)} frames)")
    return 0


def _assemble(paths: list[Path], durations: list[int], destination: Path) -> None:
    """Write the GIF with ffmpeg when it is available, else with Pillow."""
    if shutil.which("ffmpeg") is not None and _assemble_with_ffmpeg(paths, durations, destination):
        return
    images = [Image.open(path).convert("P", palette=Image.ADAPTIVE, colors=128) for path in paths]
    images[0].save(
        destination,
        save_all=True,
        append_images=images[1:],
        duration=durations,
        loop=0,
        optimize=True,
    )


def _assemble_with_ffmpeg(paths: list[Path], durations: list[int], destination: Path) -> bool:
    """Build the GIF through a generated palette, which halves the file size."""
    workspace = paths[0].parent
    # ffmpeg runs inside the frame directory, so the output path cannot be
    # relative to the caller's working directory.
    destination = destination.resolve()
    listing = workspace / "frames.txt"
    listing.write_text(
        "".join(
            f"file '{path.name}'\nduration {duration / 1000:.2f}\n"
            for path, duration in zip(paths, durations, strict=True)
        )
        # Concat demuxer ignores the last frame's duration unless it is repeated.
        + f"file '{paths[-1].name}'\n"
    )
    palette = workspace / "palette.png"
    common = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y"]
    build_palette = [
        *common, "-f", "concat", "-safe", "0", "-i", str(listing),
        "-vf", "palettegen=max_colors=128:stats_mode=diff", str(palette),
    ]  # fmt: skip
    build_gif = [
        *common, "-f", "concat", "-safe", "0", "-i", str(listing), "-i", str(palette),
        "-lavfi", "paletteuse=dither=bayer:bayer_scale=4", str(destination),
    ]  # fmt: skip
    for command in (build_palette, build_gif):
        if subprocess.run(command, cwd=workspace, check=False).returncode != 0:
            return False
    return destination.exists()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
