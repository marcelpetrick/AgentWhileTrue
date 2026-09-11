# SPDX-FileCopyrightText: 2026 Marcel Petrick
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Claude paid-choice recognition stays tied to its documented limit block."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from agent_watch import providers
from agent_watch.providers import ActionKind
from agent_watch.states import SessionState

BERLIN = ZoneInfo("Europe/Berlin")
NOW = datetime(2026, 9, 10, 23, 33, tzinfo=BERLIN)

# Only the paid-offer block below is transcribed from the documented real
# Claude 2.1.261 capture. The surrounding working/log lines are a regression
# construction for D8, not claimed to be a complete real screen capture.
DOCUMENTED_PAID_OFFER_BLOCK = [
    "  ⎿  You've hit your session limit · resets 8:10pm (Europe/Berlin)",
    "     /upgrade or /usage-credits to finish what you're working on.",
]

WORKING_SCREEN_WITH_LOG_TEXT = [
    "● Running tests",
    "  reason=paid-action-required:claude/usage-credits-offer",
    "  documentation mentions /upgrade and /usage-credits",
    "● Tests passed",
    "",
    "\N{HEAVY RIGHT-POINTING ANGLE QUOTATION MARK ORNAMENT} ",
]

EXACT_SAFE_WAIT_MENU = [
    "  ⎿  You've hit your session limit · resets 3:20am (Europe/Berlin)",
    "",
    "   What do you want to do?",
    "",
    "   \N{HEAVY RIGHT-POINTING ANGLE QUOTATION MARK ORNAMENT} 1. Stop and wait for limit to reset",
    "     2. Wait here, then continue automatically at 3:20am",
    "     3. Upgrade your plan",
    "",
    "   Enter to confirm · Esc to cancel",
]


def test_paid_reason_and_commands_in_working_output_stay_active() -> None:
    result = providers.CLAUDE.recognise(WORKING_SCREEN_WITH_LOG_TEXT, now=NOW)

    assert result.state is SessionState.ACTIVE
    assert result.matches == ()
    assert result.vetoes == ()


def test_own_paid_reason_after_latest_work_marker_stays_active() -> None:
    screen = [
        "● Running tests",
        "  decision=paid-action-required:claude/usage-credits-offer",
        "",
        "\N{HEAVY RIGHT-POINTING ANGLE QUOTATION MARK ORNAMENT} ",
    ]
    result = providers.CLAUDE.recognise(screen, now=NOW)

    assert result.state is SessionState.ACTIVE
    assert result.matches == ()
    assert result.vetoes == ()


def test_documented_limit_offer_remains_a_paid_action_veto() -> None:
    prompt = "\N{HEAVY RIGHT-POINTING ANGLE QUOTATION MARK ORNAMENT} "
    result = providers.CLAUDE.recognise([*DOCUMENTED_PAID_OFFER_BLOCK, "", prompt], now=NOW)

    assert result.state is SessionState.LIMIT_BLOCKED
    assert "claude/usage-credits-offer" in result.matched_ids
    assert "paid-action-required:claude/usage-credits-offer" in result.vetoes


def test_safe_wait_menu_survives_old_paid_reason_log_text() -> None:
    screen = [
        "  old log: paid-action-required:claude/usage-credits-offer /upgrade",
        "",
        *EXACT_SAFE_WAIT_MENU,
    ]
    result = providers.CLAUDE.recognise(screen, now=NOW)

    assert result.state is SessionState.LIMIT_BLOCKED
    assert result.action is not None
    assert result.action.kind is ActionKind.ARROW_DOWN_THEN_ENTER
    assert "claude/arm-automatic-wait" in result.matched_ids
    assert "claude/usage-credits-offer" not in result.matched_ids
    assert result.vetoes == ("paid-action-required:claude/upgrade-plan-offer",)


def test_complete_old_paid_block_does_not_poison_new_working_turn() -> None:
    screen = [
        *DOCUMENTED_PAID_OFFER_BLOCK,
        "",
        "\N{HEAVY RIGHT-POINTING ANGLE QUOTATION MARK ORNAMENT} continue",
        "● Working on the requested change",
        "● Tests passed",
        "",
        "\N{HEAVY RIGHT-POINTING ANGLE QUOTATION MARK ORNAMENT} ",
    ]
    result = providers.CLAUDE.recognise(screen, now=NOW)

    assert result.state is SessionState.ACTIVE
    assert result.matches == ()
    assert result.vetoes == ()


def test_complete_old_paid_block_does_not_veto_latest_safe_menu() -> None:
    result = providers.CLAUDE.recognise(
        [*DOCUMENTED_PAID_OFFER_BLOCK, "", *EXACT_SAFE_WAIT_MENU], now=NOW
    )

    assert result.action is not None
    assert result.action.kind is ActionKind.ARROW_DOWN_THEN_ENTER
    assert "claude/usage-credits-offer" not in result.matched_ids
    assert result.vetoes == ("paid-action-required:claude/upgrade-plan-offer",)


def test_paid_command_near_ready_prompt_still_fails_closed() -> None:
    screen = [
        "● Usage limit has reset · press enter to continue",
        "  Run /usage-credits to continue with paid usage",
        "",
        "\N{HEAVY RIGHT-POINTING ANGLE QUOTATION MARK ORNAMENT} ",
    ]
    result = providers.CLAUDE.recognise(screen, now=NOW)

    assert result.state is SessionState.READY_TO_RESUME
    assert result.action is not None
    assert result.vetoes == ("paid-action-required:claude/usage-credits-offer",)


def test_paid_menu_with_cursor_off_safe_item_fails_closed() -> None:
    unsafe_menu = [
        line.replace(
            "   \N{HEAVY RIGHT-POINTING ANGLE QUOTATION MARK ORNAMENT} 1.",
            "     1.",
        )
        for line in EXACT_SAFE_WAIT_MENU
    ]
    result = providers.CLAUDE.recognise(unsafe_menu, now=NOW)

    assert result.state is SessionState.LIMIT_BLOCKED
    assert result.action is None
    assert "claude/arm-automatic-wait" not in result.matched_ids
    assert result.vetoes == ("paid-action-required:claude/upgrade-plan-offer",)
