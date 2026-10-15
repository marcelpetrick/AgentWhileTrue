# SPDX-FileCopyrightText: 2026 Marcel Petrick
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Codex auto-yes accepts only its exact 0.162.1 one-turn tool menus."""

from datetime import UTC, datetime

import pytest

from agent_while_true import providers
from agent_while_true.states import SessionState
from tests import screens

NOW = datetime(2026, 10, 15, 12, 0, tzinfo=UTC)


def _recognise(lines: list[str]):
    return providers.CODEX.recognise(lines, now=NOW)


@pytest.mark.parametrize(
    "screen",
    [
        screens.CODEX_APPROVAL_EXEC_0_162_1,
        screens.CODEX_APPROVAL_PATCH_0_162_1,
        screens.CODEX_APPROVAL_NETWORK_0_162_1,
        screens.CODEX_APPROVAL_PERMISSIONS_0_162_1,
        screens.CODEX_APPROVAL_WRITE_STDIN_0_162_1,
        screens.CODEX_APPROVAL_EXEC_NARROW_0_162_1,
        screens.CODEX_APPROVAL_EXEC_CROSS_THREAD_0_162_1,
    ],
    ids=[
        "command",
        "patch",
        "network-once",
        "turn-permissions",
        "terminal-input",
        "narrow-command",
        "cross-thread-command",
    ],
)
def test_current_one_turn_tool_menus_are_exact(screen: list[str]) -> None:
    recognition = _recognise(screen)

    assert recognition.state is SessionState.APPROVAL_PENDING
    assert recognition.matched_ids == ("codex/tool-approval",)
    assert recognition.approval_prompt
    assert recognition.approval_fingerprint
    assert recognition.action is None
    assert not recognition.composer_empty


@pytest.mark.parametrize(
    "mutate",
    [
        lambda lines: [
            line.replace("\u203a 1.", "  1.").replace("  2.", "\u203a 2.") for line in lines
        ],
        lambda lines: [line.replace("Yes, proceed", "Yes, always proceed") for line in lines],
        lambda lines: [line.replace("No, and tell Codex", "No, but tell Codex") for line in lines],
        lambda lines: [
            line.replace("Press enter to confirm", "Enter to confirm") for line in lines
        ],
        lambda lines: [*lines, "unexpected text"],
    ],
    ids=["cursor-on-two", "reworded-yes", "reworded-no", "reworded-footer", "text-below"],
)
def test_exec_menu_variations_fail_closed(mutate) -> None:
    recognition = _recognise(mutate(list(screens.CODEX_APPROVAL_EXEC_0_162_1)))

    assert not recognition.approval_prompt
    assert recognition.approval_fingerprint == ""


@pytest.mark.parametrize(
    "screen",
    [
        [
            "  Calendar needs your approval.",
            "\u203a 1. Yes, provide the requested info (y)",
            "  2. No, but continue without it (n)",
            "  3. Cancel this request (esc)",
            "  Press enter to confirm or esc to cancel",
        ],
        [
            "  Production deployment needs your approval.",
            "\u203a 1. Verify and approve (y)",
            "  2. Cancel this request (c)",
            "  Press enter to confirm or esc to cancel",
        ],
        ["  Do you want Codex to change the model?", "\u203a 1. Yes", "  2. No"],
    ],
    ids=["mcp-elicitation", "user-verification", "arbitrary-question"],
)
def test_non_tool_or_identity_questions_remain_manual(screen: list[str]) -> None:
    recognition = _recognise(screen)

    assert not recognition.approval_prompt
    assert recognition.action is None


@pytest.mark.parametrize(
    "screen",
    [
        screens.CODEX_APPROVAL_EXEC_CLIPPED_TITLE_0_162_1,
        screens.CODEX_APPROVAL_EXEC_CLIPPED_PREVIEW_0_162_1,
    ],
    ids=["clipped-title", "hidden-command-preview"],
)
def test_a_clipped_overlay_remains_manual(screen: list[str]) -> None:
    recognition = _recognise(screen)

    assert not recognition.approval_prompt
    assert recognition.action is None


def test_the_fingerprint_binds_the_command_preview() -> None:
    first = _recognise(screens.CODEX_APPROVAL_EXEC_0_162_1)
    changed = [
        line.replace("echo hello world", "rm -rf build")
        for line in screens.CODEX_APPROVAL_EXEC_0_162_1
    ]

    assert _recognise(changed).approval_fingerprint != first.approval_fingerprint
