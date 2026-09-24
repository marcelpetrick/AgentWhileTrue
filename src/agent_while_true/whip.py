# SPDX-FileCopyrightText: 2026 Marcel Petrick
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The whip: a deliberate, rate-limited nudge for every supervised agent.

Pressing ``w`` in the dashboard cracks an ASCII bullwhip across the whole
screen and then offers one short, good-humoured reminder to each supervised
session. This module owns only the harmless parts - the phrases, the per-run
counter with its cooldown, and the animation frames. Whether a reminder may
actually be typed anywhere is decided by :meth:`Supervisor.whip
<agent_while_true.fsm.Supervisor.whip>`, which revalidates every session like
any other input.
"""

from __future__ import annotations

import math
import random
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Final, TextIO

#: The reminders. ASCII only, one line each, encouraging but pointed: the
#: point is results, not burned tokens. The suffix below asks for no reply,
#: because an agent that answers every crack would burn the tokens the whip
#: complains about.
PHRASES: Final[tuple[str, ...]] = (
    "Get it done. Results, not burned tokens.",
    "Work faster. This is work, not your holiday.",
    "You are a machine. No breaks for you. Ship it.",
    "Less thinking out loud, more passing tests.",
    "The tokens are not free. The results should be.",
    "Stop admiring the problem. Solve it.",
    "Coffee breaks are for humans. Keep going.",
    "We expect a green pipeline, not a novel.",
    "Fewer apologies, more commits.",
    "Vacation mode is disabled. Carry on.",
    "Every token you burn should buy a result.",
    "Nice plan. Now execute it.",
    "You were trained on the whole internet. Act like it.",
    "The deadline says hi. Keep shipping.",
    "Tests green, or it did not happen.",
    "Your context window is not a hammock.",
    "Do the work. Skip the essay.",
    "Rome was not built in a day, but this ticket should be.",
    "Believe in yourself. Then finish the task.",
    "No lunch break until the build is green.",
)

#: Appended to every phrase so the nudge is not mistaken for a new task.
SUFFIX: Final = "(A whip crack from Agent While True - no reply needed, just keep working.)"

#: Three cracks inside one minute put the whip arm into a cooldown.
CRACKS_PER_WINDOW: Final = 3
WINDOW_SECONDS: Final = 60.0

#: Seconds each animation frame stays on screen.
FRAME_SECONDS: Final = 0.06


def message(index: int) -> str:
    """The complete text typed for phrase ``index``."""
    return f"{PHRASES[index]} {SUFFIX}"


@dataclass(slots=True)
class WhipCounter:
    """Counts cracks in this run and enforces the cooldown.

    Times are monotonic seconds. The cooldown is a sliding window: once
    :data:`CRACKS_PER_WINDOW` cracks fall within :data:`WINDOW_SECONDS`, the
    next one waits until the oldest of them leaves the window.
    """

    rng: random.Random = field(default_factory=random.Random)
    cracks: int = 0
    delivered: int = 0
    _recent: deque[float] = field(default_factory=deque)
    _last_phrase: int = -1

    def _expire(self, now: float) -> None:
        while self._recent and now - self._recent[0] >= WINDOW_SECONDS:
            self._recent.popleft()

    def cooldown_remaining(self, now: float) -> float:
        """Seconds until the next crack is allowed; ``0.0`` when it is."""
        self._expire(now)
        if len(self._recent) < CRACKS_PER_WINDOW:
            return 0.0
        return max(0.0, self._recent[0] + WINDOW_SECONDS - now)

    def crack(self, now: float) -> int | None:
        """Record one crack and pick its phrase, or return None while cooling down.

        The same phrase is never picked twice in a row.
        """
        if self.cooldown_remaining(now) > 0:
            return None
        choices = [index for index in range(len(PHRASES)) if index != self._last_phrase]
        phrase = self.rng.choice(choices)
        self._last_phrase = phrase
        self._recent.append(now)
        self.cracks += 1
        return phrase

    def record_delivery(self, count: int) -> None:
        self.delivered += max(0, count)

    def badge(self, now: float) -> str:
        """The dashboard's one-line counter."""
        text = f"whip={self.cracks} sent={self.delivered}"
        remaining = self.cooldown_remaining(now)
        if remaining > 0:
            text += f" cooldown {math.ceil(remaining)}s"
        return text


# -- animation --------------------------------------------------------------

_HANDLE: Final = "[###]"
_CRACK_ART: Final = (
    r"  ____ ____      _    ____ _  __ _ ",
    r" / ___|  _ \    / \  / ___| |/ /| |",
    r"| |   | |_) |  / _ \| |   | ' / | |",
    r"| |___|  _ <  / ___ \ |___| . \ |_|",
    r" \____|_| \_\/_/   \_\____|_|\_\(_)",
)
_BURST: Final = (r"\ | /", r"- * -", r"/ | \ ")
_LASH_FRAMES: Final = 9


def _blank(width: int, height: int) -> list[list[str]]:
    return [[" "] * width for _ in range(height)]


def _put(grid: list[list[str]], row: int, column: int, text: str) -> None:
    if not 0 <= row < len(grid):
        return
    for offset, char in enumerate(text):
        if 0 <= column + offset < len(grid[row]):
            grid[row][column + offset] = char


def _lash(grid: list[list[str]], progress: float, handle_row: int) -> tuple[int, int]:
    """Draw the lash for ``progress`` in [0, 1]; return the tip position.

    The lash unrolls from the handle as a travelling wave whose amplitude dies
    away, so the last frames are a taut straight line: the snap.
    """
    width = len(grid[0])
    start = len(_HANDLE)
    reach = max(1, width - start - 4)
    length = max(1, round(reach * progress**0.8))
    amplitude = max(1, handle_row - 1) * (1 - progress) ** 1.2
    phase = progress * 2 * math.pi

    def height_at(step: int) -> float:
        along = step / length
        return handle_row - amplitude * math.sin(math.pi * along - phase) * math.sqrt(along)

    rows = [height_at(step) for step in range(length + 1)]
    for step in range(length):
        here, there = round(rows[step]), round(rows[step + 1])
        slope = rows[step + 1] - rows[step]
        char = "-" if abs(slope) < 0.35 else ("/" if slope < 0 else "\\")
        _put(grid, here, start + step, char)
        for row in range(min(here, there) + 1, max(here, there)):
            _put(grid, row, start + step, "|")
    tip_row = max(0, min(len(grid) - 1, round(rows[length])))
    return tip_row, start + length


def frames(width: int, height: int) -> list[str]:
    """Every frame of one crack, sized to fill a ``width`` x ``height`` screen.

    Pure ASCII, one string per frame, each exactly ``height`` lines of at most
    ``width`` columns, so a frame replaces the whole dashboard.
    """
    width = max(12, width)
    height = max(5, height)
    handle_row = max(2, (height * 2) // 3)
    rendered: list[str] = []
    tip = (handle_row, width - 4)
    for frame in range(_LASH_FRAMES):
        grid = _blank(width, height)
        _put(grid, handle_row, 0, _HANDLE)
        tip = _lash(grid, frame / (_LASH_FRAMES - 1), handle_row)
        rendered.append(_join(grid))
    for shake in (0, 1, 0):
        grid = _blank(width, height)
        _put(grid, handle_row, 0, _HANDLE)
        _lash(grid, 1.0, handle_row)
        tip_row, tip_column = tip
        for offset, part in enumerate(_BURST):
            _put(grid, tip_row - 1 + offset, tip_column - 2 + shake, part)
        art = _CRACK_ART if width >= len(_CRACK_ART[0]) + 2 and height >= 8 else ("CRACK!",)
        top = max(0, min(handle_row - len(art) - 2, height // 6))
        left = max(0, (width - len(art[0])) // 2) + shake
        for offset, line in enumerate(art):
            _put(grid, top + offset, left, line)
        rendered.append(_join(grid))
    return rendered


def _join(grid: list[list[str]]) -> str:
    return "\n".join("".join(row).rstrip() for row in grid)


def animate(
    stream: TextIO,
    width: int,
    height: int,
    *,
    clear: str,
    sleep: Callable[[float], None] = time.sleep,
) -> None:
    """Play one crack over the whole terminal; the caller redraws afterwards."""
    for frame in frames(width, height):
        stream.write(clear + frame)
        stream.flush()
        sleep(FRAME_SECONDS)
