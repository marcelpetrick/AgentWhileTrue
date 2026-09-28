# SPDX-FileCopyrightText: 2026 Marcel Petrick
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Claude Code's tool-permission prompt is recognised, shown and never resumed."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from agent_while_true import providers
from agent_while_true.config import Mode
from agent_while_true.states import SessionState
from agent_while_true.ui import session_details
from tests import harness as harness_module
from tests import screens

NOW = datetime(2026, 9, 28, 12, 0, tzinfo=UTC)
SESSION = "/Sessions/1"


def _recognise(lines: list[str]):
    return providers.CLAUDE.recognise(lines, now=NOW)


def test_the_live_yes_no_prompt_is_the_exact_tested_shape() -> None:
    recognition = _recognise(screens.CLAUDE_APPROVAL_YES_NO)

    assert recognition.state is SessionState.APPROVAL_PENDING
    assert recognition.matched_ids == ("claude/tool-approval",)
    assert recognition.approval_prompt
    assert recognition.approval_fingerprint
    # A permission prompt is not a resume prompt: nothing is proposed.
    assert recognition.action is None
    assert not recognition.composer_empty


@pytest.mark.parametrize(
    "screen",
    [screens.CLAUDE_APPROVAL_DONT_ASK_AGAIN, screens.CLAUDE_APPROVAL_CURSOR_ON_NO],
    ids=["dont-ask-again", "cursor-on-no"],
)
def test_other_menu_shapes_are_shown_but_not_exact(screen: list[str]) -> None:
    recognition = _recognise(screen)

    assert recognition.state is SessionState.APPROVAL_PENDING
    assert not recognition.approval_prompt
    assert recognition.approval_fingerprint == ""


def test_a_quoted_prompt_is_not_the_prompt() -> None:
    recognition = _recognise(screens.CLAUDE_APPROVAL_QUOTED)

    assert recognition.state is SessionState.ACTIVE
    assert recognition.matched_ids == ()
    assert not recognition.approval_prompt


@pytest.mark.parametrize(
    "mutate",
    [
        lambda lines: [*lines, "\N{HEAVY RIGHT-POINTING ANGLE QUOTATION MARK ORNAMENT} "],
        lambda lines: [line.replace("2. No", "2. Nope") for line in lines],
        lambda lines: [line.replace("1. Yes", "1. Yes please") for line in lines],
        lambda lines: [line.replace("Do you want to proceed?", "Proceed?") for line in lines],
        lambda lines: [line for line in lines if not line.startswith("─")],
    ],
    ids=["text-below-footer", "reworded-no", "reworded-yes", "reworded-question", "no-top-rule"],
)
def test_every_variation_of_the_exact_shape_fails_closed(mutate) -> None:
    assert not _recognise(mutate(list(screens.CLAUDE_APPROVAL_YES_NO))).approval_prompt


def test_the_box_fingerprint_ignores_the_redrawing_transcript_above() -> None:
    first = _recognise(screens.CLAUDE_APPROVAL_YES_NO)
    spinner = [
        line.replace("Waiting for 1 background agent", "Waiting for 2 background agents")
        for line in screens.CLAUDE_APPROVAL_YES_NO
    ]
    other_command = [
        line.replace("head -30", "rm -rf build") for line in screens.CLAUDE_APPROVAL_YES_NO
    ]

    assert _recognise(spinner).approval_fingerprint == first.approval_fingerprint
    assert _recognise(other_command).approval_fingerprint != first.approval_fingerprint


def _kit(tmp_path: Path, screen: list[str], *, mode: Mode = Mode.AUTO):
    kit = harness_module.build(tmp_path, mode=mode, now=NOW)
    info = kit.inspector.add_claude(4101)
    ref = kit.terminal.add(
        SESSION, shell_pid=100, foreground_pid=4101, screen=list(screen), title="api : claude"
    )
    kit.supervisor.select(ref, info.identity, "claude", "api : claude")
    return kit, ref.key()


def test_full_auto_never_answers_a_permission_prompt_on_its_own(tmp_path: Path) -> None:
    kit, key = _kit(tmp_path, screens.CLAUDE_APPROVAL_YES_NO)

    for _ in range(3):
        decisions = kit.supervisor.tick()
        kit.clock.advance(5)
        harness_module.refresh_quota(kit)

    assert kit.sent == []
    session = kit.supervisor.sessions[key]
    assert session.state is SessionState.APPROVAL_PENDING
    assert session.approval_exact
    assert not decisions[0].allowed
    log = (tmp_path / "agent-while-true.log").read_text(encoding="utf-8")
    assert "new=APPROVAL_PENDING" in log
    # Not a resume situation, so not a resume refusal either.
    assert "resume_refused" not in log
    # The command itself never reaches the log.
    assert "pytest" not in log


def test_the_detail_panel_says_which_shape_is_waiting(tmp_path: Path) -> None:
    kit, key = _kit(tmp_path, screens.CLAUDE_APPROVAL_DONT_ASK_AGAIN)
    kit.supervisor.tick()
    untested = session_details(kit.supervisor.sessions[key], NOW, 1.0)

    kit.terminal.set_screen(SESSION, list(screens.CLAUDE_APPROVAL_YES_NO))
    kit.supervisor.tick()
    exact = session_details(kit.supervisor.sessions[key], NOW, 1.0)

    assert any("untested shape; answer it in its tab" in line for line in untested)
    assert "Approval: exact Yes/No permission prompt" in exact
