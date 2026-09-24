# SPDX-FileCopyrightText: 2026 Marcel Petrick
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The whip's phrases, counter, cooldown and ASCII animation."""

from __future__ import annotations

import io
import random

import pytest

from agent_while_true import whip


def test_phrases_are_single_ascii_lines_and_messages_ask_for_no_reply() -> None:
    assert len(whip.PHRASES) == 40
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


def test_five_cracks_in_a_minute_start_a_cooldown() -> None:
    counter = whip.WhipCounter(rng=random.Random(1))
    assert whip.CRACKS_PER_WINDOW == 5
    for second in (100.0, 110.0, 120.0, 130.0):
        assert counter.crack(second) is not None
        assert counter.cooldown_remaining(second) == 0.0
    assert counter.crack(140.0) is not None

    assert counter.cooldown_remaining(140.0) == pytest.approx(20.0)
    assert counter.crack(159.0) is None
    assert counter.cracks == 5
    assert "cooldown 1s" in counter.badge(159.5)

    # The oldest crack leaves the window at 160s; the next one is allowed.
    assert counter.cooldown_remaining(160.0) == 0.0
    assert counter.crack(160.0) is not None
    assert counter.cracks == 6
    # 110 through 160 are now five cracks inside one minute again.
    assert counter.cooldown_remaining(160.0) == pytest.approx(10.0)


def test_cracks_spread_over_more_than_a_minute_never_cool_down() -> None:
    counter = whip.WhipCounter(rng=random.Random(2))
    for second in range(0, 600, 21):
        assert counter.crack(float(second)) is not None
    assert counter.cracks == len(range(0, 600, 21))


def test_one_crack_offers_every_phrase_exactly_once() -> None:
    order = whip.WhipCounter(rng=random.Random(3)).crack(0.0)
    assert order is not None
    assert sorted(order) == list(range(len(whip.PHRASES)))


def test_recently_delivered_phrases_wait_at_the_back() -> None:
    counter = whip.WhipCounter(rng=random.Random(4))
    first = counter.crack(0.0)
    assert first is not None
    counter.record_delivery(first[:7])

    second = counter.crack(61.0)
    assert second is not None
    assert set(second[: len(whip.PHRASES) - 7]).isdisjoint(first[:7])
    assert second[-7:] == first[:7]


def test_only_the_most_recent_half_of_the_phrases_is_held_back() -> None:
    counter = whip.WhipCounter(rng=random.Random(5))
    counter.record_delivery(list(range(len(whip.PHRASES))))
    order = counter.crack(0.0)
    assert order is not None
    held = order[-whip.RECENT_PHRASES :]
    assert held == list(range(len(whip.PHRASES) - whip.RECENT_PHRASES, len(whip.PHRASES)))
    # Delivering a held phrase again moves it to the very back.
    counter.record_delivery([held[0]])
    again = counter.crack(61.0)
    assert again is not None
    assert again[-1] == held[0]


def test_cracks_stay_varied_across_a_long_session() -> None:
    counter = whip.WhipCounter(rng=random.Random(6))
    seen: list[int] = []
    for step in range(12):
        order = counter.crack(float(step) * 61)
        assert order is not None
        counter.record_delivery(order[:3])
        seen.extend(order[:3])
    for index in range(len(seen) - 3):
        assert seen[index] not in seen[index + 1 : index + 20]


def test_badge_counts_cracks_and_deliveries() -> None:
    counter = whip.WhipCounter(rng=random.Random(7))
    assert counter.badge(0.0) == "whip=0 sent=0"
    counter.crack(0.0)
    counter.record_delivery([2, 5])
    counter.record_delivery([])
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
