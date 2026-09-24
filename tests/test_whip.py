# SPDX-FileCopyrightText: 2026 Marcel Petrick
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The whip's phrases, counter, cooldown and ASCII animation."""

from __future__ import annotations

import io
import itertools
import random

import pytest

from agent_while_true import whip


def test_phrases_are_single_ascii_lines_and_messages_ask_for_no_reply() -> None:
    assert len(whip.PHRASES) >= 10
    assert len(set(whip.PHRASES)) == len(whip.PHRASES)
    for index, phrase in enumerate(whip.PHRASES):
        text = whip.message(index)
        assert text.isascii()
        assert "\n" not in text
        assert "\r" not in text
        assert "\x1b" not in text
        assert text.startswith(phrase)
        assert text.endswith(whip.SUFFIX)
    assert "no reply needed" in whip.SUFFIX


def test_three_cracks_in_a_minute_start_a_cooldown() -> None:
    counter = whip.WhipCounter(rng=random.Random(1))
    assert counter.crack(100.0) is not None
    assert counter.crack(110.0) is not None
    assert counter.cooldown_remaining(110.0) == 0.0
    assert counter.crack(120.0) is not None

    assert counter.cooldown_remaining(120.0) == pytest.approx(40.0)
    assert counter.crack(159.0) is None
    assert counter.cracks == 3
    assert "cooldown 1s" in counter.badge(159.5)

    # The oldest crack leaves the window at 160s; the next one is allowed.
    assert counter.cooldown_remaining(160.0) == 0.0
    assert counter.crack(160.0) is not None
    assert counter.cracks == 4
    # 110, 120 and 160 are now inside one minute again.
    assert counter.cooldown_remaining(160.0) == pytest.approx(10.0)


def test_cracks_spread_over_more_than_a_minute_never_cool_down() -> None:
    counter = whip.WhipCounter(rng=random.Random(2))
    for second in range(0, 600, 21):
        assert counter.crack(float(second)) is not None
    assert counter.cracks == len(range(0, 600, 21))


def test_the_same_phrase_is_never_picked_twice_in_a_row() -> None:
    counter = whip.WhipCounter(rng=random.Random(3))
    picked = [counter.crack(float(step) * 61) for step in range(200)]
    assert all(first != second for first, second in itertools.pairwise(picked))
    assert len(set(picked)) > len(whip.PHRASES) // 2


def test_badge_counts_cracks_and_deliveries() -> None:
    counter = whip.WhipCounter(rng=random.Random(4))
    assert counter.badge(0.0) == "whip=0 sent=0"
    counter.crack(0.0)
    counter.record_delivery(2)
    counter.record_delivery(-5)
    assert counter.badge(1.0) == "whip=1 sent=2"


@pytest.mark.parametrize(("width", "height"), [(168, 40), (80, 24), (40, 10), (1, 1)])
def test_frames_are_ascii_and_fill_the_screen(width: int, height: int) -> None:
    rendered = whip.frames(width, height)
    assert len(rendered) >= 10
    columns, rows = max(12, width), max(5, height)
    for frame in rendered:
        assert frame.isascii()
        lines = frame.split("\n")
        assert len(lines) == rows
        assert all(len(line) <= columns for line in lines)
    assert "[###]" in rendered[0]
    assert "*" in rendered[-1]
    assert rendered[0] != rendered[len(rendered) // 2]


def test_the_crack_uses_big_letters_only_where_they_fit() -> None:
    assert "____" in whip.frames(80, 24)[-1]
    small = whip.frames(20, 6)[-1]
    assert "CRACK!" in small
    assert "____" not in small


def test_animate_draws_every_frame_over_a_cleared_screen() -> None:
    stream = io.StringIO()
    pauses: list[float] = []
    whip.animate(stream, 80, 24, clear="<CLS>", sleep=pauses.append)
    frame_count = len(whip.frames(80, 24))
    assert stream.getvalue().count("<CLS>") == frame_count
    assert pauses == [whip.FRAME_SECONDS] * frame_count
    assert sum(pauses) < 1.0


def test_drawing_off_the_screen_is_clipped_rather_than_wrapped() -> None:
    grid = [[" "] * 4 for _ in range(2)]
    whip._put(grid, -1, 0, "xx")
    whip._put(grid, 2, 0, "xx")
    whip._put(grid, 0, 3, "abc")
    whip._put(grid, 1, -1, "abc")
    assert grid == [[" ", " ", " ", "a"], ["b", "c", " ", " "]]
