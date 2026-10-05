# SPDX-FileCopyrightText: 2026 Marcel Petrick
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Claude Code 2.1.283's new limit headlines: waits that end, and caps that do not."""

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from agent_while_true import providers
from agent_while_true.providers import ActionKind
from agent_while_true.states import SessionState
from tests import screens

NOW = datetime(2026, 9, 29, 19, 0, tzinfo=ZoneInfo("Europe/Berlin"))
WAIT_MENU = [
    "",
    "   What do you want to do?",
    "",
    "   \N{HEAVY RIGHT-POINTING ANGLE QUOTATION MARK ORNAMENT} 1. Stop and wait for limit to reset",
    "     2. Wait here, then continue automatically shortly",
    "     3. Upgrade your plan",
    "",
    "   Enter to confirm · Esc to cancel",
]


def _recognise(lines: list[str]):
    return providers.CLAUDE.recognise(lines, now=NOW)


@pytest.mark.parametrize(
    "line", screens.CLAUDE_2_1_283_WINDOW_LIMITS.values(), ids=screens.CLAUDE_2_1_283_WINDOW_LIMITS
)
def test_a_window_limit_blocks_and_carries_its_reset(line: str) -> None:
    recognition = _recognise([line, "", "\N{HEAVY RIGHT-POINTING ANGLE QUOTATION MARK ORNAMENT} "])

    assert recognition.state is SessionState.LIMIT_BLOCKED
    assert recognition.vetoes == ()
    assert recognition.reset_at is not None
    assert recognition.action is None


@pytest.mark.parametrize(
    "line", screens.CLAUDE_2_1_283_WINDOW_LIMITS.values(), ids=screens.CLAUDE_2_1_283_WINDOW_LIMITS
)
def test_a_window_limit_banner_lets_claude_arm_its_own_wait(line: str) -> None:
    recognition = _recognise([line, *WAIT_MENU])

    assert recognition.action is not None
    assert recognition.action.kind is ActionKind.ARROW_DOWN_THEN_ENTER


@pytest.mark.parametrize(
    "line", screens.CLAUDE_2_1_283_ADMIN_LIMITS.values(), ids=screens.CLAUDE_2_1_283_ADMIN_LIMITS
)
def test_a_cap_no_wait_ends_is_a_veto(line: str) -> None:
    alone = _recognise([line, "", "\N{HEAVY RIGHT-POINTING ANGLE QUOTATION MARK ORNAMENT} "])
    menu = _recognise([line, *WAIT_MENU])

    assert alone.state is SessionState.LIMIT_BLOCKED
    assert any(veto.startswith("paid-action-required:") for veto in alone.vetoes)
    # Arming the wait menu tolerates only its own upgrade item, never a cap.
    assert any(
        veto.startswith("paid-action-required:claude/admin-")
        or veto.startswith("paid-action-required:claude/credits-")
        for veto in menu.vetoes
    )


def test_quoted_headlines_inside_a_sentence_still_do_not_match_the_prompt_region() -> None:
    """A newer turn below an old headline starts a new region, as before."""
    recognition = _recognise(
        [
            screens.CLAUDE_2_1_283_ADMIN_LIMITS["org-out"],
            "● All tests pass.",
            "\N{HEAVY RIGHT-POINTING ANGLE QUOTATION MARK ORNAMENT} ",
        ]
    )

    assert recognition.state is SessionState.ACTIVE
    assert recognition.vetoes == ()


@pytest.mark.parametrize(
    "line",
    [
        "  ⚠ Continuing automatically at 7pm · esc to cancel",
        "  ⚠ Continuing automatically at 6:50pm · esc to cancel",
        "  ⚠ Usage limit reached · continuing automatically at 7pm · esc to cancel",
        "  ⚠ Usage limit reached · continuing automatically at Oct 3, 7pm · esc to cancel",
        "  ⚠ Usage limit reached · continuing automatically at Oct 3, 6:50pm · esc to cancel",
        "  ⚠ Continuing automatically when it resets · esc to cancel",
        "  ⚠ Usage limit reached · continuing automatically shortly · esc to cancel",
    ],
    ids=["on-the-hour", "minutes", "started-hour", "date-hour", "date-minutes", "when", "shortly"],
)
def test_every_armed_wait_wording_makes_the_supervisor_stand_down(line: str) -> None:
    """Claude formats an on-the-hour reset as "7pm" and one a day out as "Oct 3, 7pm".

    Strings of 2.1.283 and 2.1.284: the formatter drops the minutes when they
    are zero. A pattern that required "6:50pm" missed the armed wait, and the
    supervisor would not have stood down while Claude waited by itself.
    """
    recognition = _recognise(["● Waiting.", line])

    assert any(veto.startswith("provider-resumes-itself:") for veto in recognition.vetoes)
