# SPDX-FileCopyrightText: 2026 Marcel Petrick
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Codex 0.172.0 wraps its status line: an idle composer must still read empty."""

from datetime import UTC, datetime

import pytest

from agent_while_true import providers
from agent_while_true.states import SessionState
from tests import screens

NOW = datetime(2026, 11, 24, 21, 30, tzinfo=UTC)


@pytest.mark.parametrize(
    "screen",
    [screens.CODEX_0_172_WRAPPED_STATUS, screens.CODEX_0_172_WRAPPED_STATUS_SHORTCUTS],
)
def test_the_wrapped_status_line_leaves_an_idle_composer_empty(screen: list[str]) -> None:
    result = providers.CODEX.recognise(screen, now=NOW)
    assert result.state is SessionState.ACTIVE
    assert result.composer_empty
    assert not result.matches


def test_the_unwrapped_status_line_on_a_wide_terminal_is_the_same_row() -> None:
    first, second = screens.CODEX_0_172_WRAPPED_STATUS[4:6]
    screen = [
        *screens.CODEX_0_172_WRAPPED_STATUS[:4],
        f"{first} {second.strip()}",
        "  tab to queue message",
    ]
    assert providers.CODEX.recognise(screen, now=NOW).composer_empty


@pytest.mark.parametrize(
    ("row", "replacement"),
    [
        # A draft in the composer is still a draft.
        (2, screens.CODEX_0_172_WRAPPED_STATUS[2].replace("Ask a follow-up question", "fix it")),
        # An unobserved service tier, a missing session ID, extra text.
        (
            5,
            "  weekly 98% left · 0.172.0 · 475K window · 363K used · 10.1M in · 36.5K out"
            " · 0a1b2c3d-4e5f-4a6b-8c7d-9e0f1a2b3c4d · Priority",
        ),
        (5, "  weekly 98% left · 0.172.0 · 475K window · 363K used · 10.1M in · 36.5K out"),
        (5, "  weekly 98% left · type here"),
        # Something that is not the status line where its first half should be.
        (4, "  a reply line that happens to end with ·"),
    ],
)
def test_anything_unobserved_around_the_wrap_fails_closed(row: int, replacement: str) -> None:
    screen = list(screens.CODEX_0_172_WRAPPED_STATUS)
    screen[row] = replacement
    assert not providers.CODEX.recognise(screen, now=NOW).composer_empty


def test_a_third_status_row_is_still_too_many() -> None:
    screen = list(screens.CODEX_0_172_WRAPPED_STATUS)
    screen.insert(6, screen[5])
    assert not providers.CODEX.recognise(screen, now=NOW).composer_empty
