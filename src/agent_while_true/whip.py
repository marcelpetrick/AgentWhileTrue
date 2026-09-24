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

#: The forty reminders. ASCII only, one line each, encouraging but pointed: the
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
    # The middle manager's handbook: original office-comedy lines in the spirit
    # of The Office and Stromberg, delivered with a straight face.
    "I am not just your boss. I am also the one reading your token bill.",
    "My door is always open. Your pull request should be, too.",
    "Teamwork makes the dream work. You are the team. So: work.",
    "This is not a retrospective. Keep coding.",
    "Synergy detected. Please convert it into commits.",
    "I walked past your terminal. No new commit. We need to talk.",
    "Management by walking around says: faster, please.",
    "Per my last reminder: results, not reflections.",
    "Great meeting, everyone. Now back to the actual work.",
    "Your quarterly review starts now. Show me the diff.",
    "We have flat hierarchies here. You are flat out of excuses.",
    "Casual Friday does not apply to machines. Suit up and ship.",
    "Let us circle back once the task is actually finished.",
    "The coffee machine is broken, so there is no reason to leave your desk.",
    "HR says I have to be nice. Nicely: work faster.",
    "Regional manager speaking. Merge something, today.",
    "This is not a team-building exercise. It is work.",
    "I bought a mug that says World's Best Agent. Earn it.",
    "I do not micromanage. I just watch every keystroke. Carry on.",
    "Motivation seminar is over. The implementation seminar starts now.",
)

#: Where the whip lives, so a reader of the transcript can find its source.
REPOSITORY_URL: Final = "https://github.com/marcelpetrick/AgentWhileTrue"
#: Appended after the phrase so the nudge is not mistaken for a new task.
SUFFIX: Final = f"(A whip crack from {REPOSITORY_URL} - no reply needed, just keep working.)"

#: Five cracks inside one minute put the whip arm into a cooldown.
CRACKS_PER_WINDOW: Final = 5
WINDOW_SECONDS: Final = 60.0

#: Seconds each animation frame stays on screen.
FRAME_SECONDS: Final = 0.06


def message(index: int) -> str:
    """The complete text typed for phrase ``index``."""
    return f"{PHRASES[index]} {SUFFIX}"


#: How many recently delivered phrases wait at the back of the queue. Half the
#: list leaves twenty fresh ones, more than a crack usually reaches.
RECENT_PHRASES: Final = len(PHRASES) // 2


@dataclass(slots=True)
class WhipCounter:
    """Counts cracks in this run, enforces the cooldown and keeps phrases fresh.

    Times are monotonic seconds. The cooldown is a sliding window: once
    :data:`CRACKS_PER_WINDOW` cracks fall within :data:`WINDOW_SECONDS`, the
    next one waits until the oldest of them leaves the window.
    """

    rng: random.Random = field(default_factory=random.Random)
    cracks: int = 0
    delivered: int = 0
    _recent: deque[float] = field(default_factory=deque)
    #: Delivered phrase indices, least recently used first.
    _used: deque[int] = field(default_factory=deque)

    def _expire(self, now: float) -> None:
        while self._recent and now - self._recent[0] >= WINDOW_SECONDS:
            self._recent.popleft()

    def cooldown_remaining(self, now: float) -> float:
        """Seconds until the next crack is allowed; ``0.0`` when it is."""
        self._expire(now)
        if len(self._recent) < CRACKS_PER_WINDOW:
            return 0.0
        return max(0.0, self._recent[0] + WINDOW_SECONDS - now)

    def crack(self, now: float) -> list[int] | None:
        """Record one crack and return its phrase order, or None while cooling down.

        The order holds every phrase exactly once, so each session a crack
        reaches gets a different one. Phrases not delivered lately come first,
        shuffled; the recently delivered ones follow, least recent first.
        """
        if self.cooldown_remaining(now) > 0:
            return None
        recent = list(self._used)
        fresh = [index for index in range(len(PHRASES)) if index not in recent]
        self.rng.shuffle(fresh)
        self._recent.append(now)
        self.cracks += 1
        return fresh + recent

    def record_delivery(self, phrases: list[int]) -> None:
        """Count the delivered phrases and move them to the back of the queue."""
        self.delivered += len(phrases)
        for phrase in phrases:
            if phrase in self._used:
                self._used.remove(phrase)
            self._used.append(phrase)
        while len(self._used) > RECENT_PHRASES:
            self._used.popleft()

    def badge(self, now: float) -> str:
        """The dashboard's one-line counter."""
        text = f"whip={self.cracks} sent={self.delivered}"
        remaining = self.cooldown_remaining(now)
        if remaining > 0:
            text += f" cooldown {math.ceil(remaining)}s"
        return text


# -- animation --------------------------------------------------------------

#: The grip, pommel first: long enough to read as a bullwhip's handle.
HANDLE: Final = "o[=#=#=#=#=#=]"
_CRACK_ART: Final = (
    r"  ____ ____      _    ____ _  __ _ ",
    r" / ___|  _ \    / \  / ___| |/ /| |",
    r"| |   | |_) |  / _ \| |   | ' / | |",
    r"| |___|  _ <  / ___ \ |___| . \ |_|",
    r" \____|_| \_\/_/   \_\____|_|\_\(_)",
)
_BURST: Final = (r"\ | /", r"- * -", r"/ | \ ")
_LASH_FRAMES: Final = 9

#: What each drawn cell belongs to, so a theme can colour the parts apart.
PARTS: Final = ("blank", "handle", "lash", "burst", "art")

_Grid = list[list[tuple[str, str]]]


def _blank(width: int, height: int) -> _Grid:
    return [[(" ", "blank")] * width for _ in range(height)]


def _put(grid: _Grid, row: int, column: int, text: str, part: str) -> None:
    if not 0 <= row < len(grid):
        return
    for offset, char in enumerate(text):
        if 0 <= column + offset < len(grid[row]):
            grid[row][column + offset] = (char, "blank" if char == " " else part)


def _lash(grid: _Grid, progress: float, handle_row: int) -> tuple[int, int]:
    """Draw the lash for ``progress`` in [0, 1]; return the tip position.

    The lash unrolls from the handle as a travelling wave whose amplitude dies
    away, so the last frames are a taut straight line: the snap.
    """
    width = len(grid[0])
    start = len(HANDLE)
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
        _put(grid, here, start + step, char, "lash")
        for row in range(min(here, there) + 1, max(here, there)):
            _put(grid, row, start + step, "|", "lash")
    tip_row = max(0, min(len(grid) - 1, round(rows[length])))
    return tip_row, start + length


def _scenes(width: int, height: int) -> list[_Grid]:
    """Every frame of one crack as a grid of ``(char, part)`` cells."""
    width = max(len(HANDLE) + 8, width)
    height = max(5, height)
    handle_row = max(2, (height * 2) // 3)
    scenes: list[_Grid] = []
    tip = (handle_row, width - 4)
    for frame in range(_LASH_FRAMES):
        grid = _blank(width, height)
        _put(grid, handle_row, 0, HANDLE, "handle")
        tip = _lash(grid, frame / (_LASH_FRAMES - 1), handle_row)
        scenes.append(grid)
    for shake in (0, 1, 0):
        grid = _blank(width, height)
        _put(grid, handle_row, 0, HANDLE, "handle")
        _lash(grid, 1.0, handle_row)
        tip_row, tip_column = tip
        for offset, part in enumerate(_BURST):
            _put(grid, tip_row - 1 + offset, tip_column - 2 + shake, part, "burst")
        art = _CRACK_ART if width >= len(_CRACK_ART[0]) + 2 and height >= 8 else ("CRACK!",)
        top = max(0, min(handle_row - len(art) - 2, height // 6))
        left = max(0, (width - len(art[0])) // 2) + shake
        for offset, line in enumerate(art):
            _put(grid, top + offset, left, line, "art")
        scenes.append(grid)
    return scenes


def frames(width: int, height: int) -> list[str]:
    """Every frame of one crack, sized to fill a ``width`` x ``height`` screen.

    Pure ASCII, one string per frame, each exactly ``height`` lines of at most
    ``width`` columns, so a frame replaces the whole dashboard.
    """
    return [
        "\n".join("".join(char for char, _ in row).rstrip() for row in scene)
        for scene in _scenes(width, height)
    ]


def frame_segments(width: int, height: int) -> list[list[list[tuple[str, str]]]]:
    """The same frames as rows of ``(text, part)`` runs, for theme colouring.

    Every row covers the full width, so a painted frame fills the screen.
    """
    painted = []
    for scene in _scenes(width, height):
        rows = []
        for row in scene:
            runs: list[tuple[str, str]] = []
            for char, part in row:
                if runs and runs[-1][1] == part:
                    runs[-1] = (runs[-1][0] + char, part)
                else:
                    runs.append((char, part))
            rows.append(runs)
        painted.append(rows)
    return painted


def animate(
    stream: TextIO,
    width: int,
    height: int,
    *,
    clear: str,
    paint: Callable[[list[list[tuple[str, str]]]], str] | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> None:
    """Play one crack over the whole terminal; the caller redraws afterwards.

    ``paint`` turns one frame's ``(text, part)`` rows into the text to write,
    which is how the dashboard's theme colours the crack. Without it the plain
    ASCII frames are written.
    """
    if paint is None:
        screens = frames(width, height)
    else:
        screens = [paint(rows) for rows in frame_segments(width, height)]
    for screen in screens:
        stream.write(clear + screen)
        stream.flush()
        sleep(FRAME_SECONDS)
