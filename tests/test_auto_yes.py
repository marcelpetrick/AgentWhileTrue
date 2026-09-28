# SPDX-FileCopyrightText: 2026 Marcel Petrick
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Auto-yes answers only the exact, revalidated Claude Code Yes/No prompt, once."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from agent_while_true.config import Mode
from agent_while_true.fsm import APPROVE_KEYSTROKES
from agent_while_true.states import SessionState
from agent_while_true.terminal.base import TerminalUnavailableError
from tests import harness as harness_module
from tests import screens

NOW = datetime(2026, 9, 28, 12, 0, tzinfo=UTC)
CLAUDE = "/Sessions/1"
CODEX = "/Sessions/2"


def _kit(tmp_path: Path, screen: list[str], *, mode: Mode = Mode.AUTO):
    kit = harness_module.build(tmp_path, mode=mode, now=NOW)
    info = kit.inspector.add_claude(4101)
    ref = kit.terminal.add(
        CLAUDE, shell_pid=100, foreground_pid=4101, screen=list(screen), title="api : claude"
    )
    kit.supervisor.select(ref, info.identity, "claude", "api : claude")
    return kit, ref.key()


def _scan(kit) -> dict[str, str]:
    """One dashboard scan with auto-yes on: tick, then answer what it saw."""
    kit.supervisor.tick()
    return kit.supervisor.approve_pending()


def _log(tmp_path: Path) -> str:
    return (tmp_path / "agent-while-true.log").read_text(encoding="utf-8")


@pytest.mark.parametrize("mode", [Mode.AUTO, Mode.ASK])
def test_the_exact_prompt_is_answered_with_one_enter(tmp_path: Path, mode: Mode) -> None:
    kit, key = _kit(tmp_path, screens.CLAUDE_APPROVAL_YES_NO, mode=mode)

    assert _scan(kit) == {key: "approved"}

    assert APPROVE_KEYSTROKES == "\r"
    assert kit.sent == [(CLAUDE, "\r")]
    log = _log(tmp_path)
    assert "approval_sent" in log
    # The command stays out of the log; only identifiers and the box fingerprint.
    assert "pytest" not in log
    assert "head -30" not in log


def test_observe_mode_never_answers(tmp_path: Path) -> None:
    kit, key = _kit(tmp_path, screens.CLAUDE_APPROVAL_YES_NO, mode=Mode.OBSERVE)

    assert _scan(kit) == {key: "observe-mode"}
    assert kit.sent == []


@pytest.mark.parametrize(
    "screen",
    [
        screens.CLAUDE_APPROVAL_DONT_ASK_AGAIN,
        screens.CLAUDE_APPROVAL_CURSOR_ON_NO,
        screens.CLAUDE_APPROVAL_QUOTED,
        screens.CLAUDE_IDLE_COMPOSER,
        screens.CLAUDE_LIMIT_MENU,
    ],
    ids=["dont-ask-again", "cursor-on-no", "quoted", "idle", "limit-menu"],
)
def test_no_other_screen_is_even_attempted(tmp_path: Path, screen: list[str]) -> None:
    kit, _ = _kit(tmp_path, screen)

    assert _scan(kit) == {}
    # The limit menu may still be armed by the resume path; auto-yes sends nothing.
    assert (CLAUDE, APPROVE_KEYSTROKES) not in kit.sent
    assert "approval_" not in _log(tmp_path)


def test_the_same_box_is_answered_once_until_it_leaves_the_screen(tmp_path: Path) -> None:
    kit, key = _kit(tmp_path, screens.CLAUDE_APPROVAL_YES_NO)
    assert _scan(kit) == {key: "approved"}

    # Claude has not redrawn yet: the answered box is still there.
    assert _scan(kit) == {}
    assert kit.supervisor.approve(key, kit.supervisor.sessions[key].approval_fingerprint) == (
        "already-approved"
    )
    assert kit.sent == [(CLAUDE, "\r")]

    # The command ran, then the agent asked for the very same command again.
    kit.terminal.set_screen(CLAUDE, list(screens.CLAUDE_IDLE_COMPOSER))
    assert _scan(kit) == {}
    kit.terminal.set_screen(CLAUDE, list(screens.CLAUDE_APPROVAL_YES_NO))
    assert _scan(kit) == {key: "approved"}
    assert kit.sent == [(CLAUDE, "\r"), (CLAUDE, "\r")]


def test_a_different_command_since_the_scan_is_refused(tmp_path: Path) -> None:
    kit, key = _kit(tmp_path, screens.CLAUDE_APPROVAL_YES_NO)
    kit.supervisor.tick()
    kit.terminal.set_screen(
        CLAUDE,
        [line.replace("head -30", "rm -rf ~") for line in screens.CLAUDE_APPROVAL_YES_NO],
    )

    assert kit.supervisor.approve_pending() == {key: "prompt-changed"}
    assert kit.sent == []


def test_a_menu_changed_since_the_scan_is_refused(tmp_path: Path) -> None:
    kit, key = _kit(tmp_path, screens.CLAUDE_APPROVAL_YES_NO)
    kit.supervisor.tick()
    kit.terminal.set_screen(CLAUDE, list(screens.CLAUDE_APPROVAL_DONT_ASK_AGAIN))

    assert kit.supervisor.approve_pending() == {key: "no-exact-approval-prompt"}
    assert kit.sent == []


def test_a_limit_on_the_same_screen_is_refused(tmp_path: Path) -> None:
    kit, key = _kit(tmp_path, screens.CLAUDE_APPROVAL_YES_NO)
    kit.supervisor.tick()
    kit.terminal.set_screen(
        CLAUDE,
        [
            screens.CLAUDE_APPROVAL_YES_NO[0],
            "  ⎿  You've hit your session limit · resets 8:10pm (Europe/Berlin)",
            *screens.CLAUDE_APPROVAL_YES_NO[1:],
        ],
    )

    assert kit.supervisor.approve_pending() == {key: "no-exact-approval-prompt"}
    assert kit.sent == []


def test_a_replaced_process_is_refused(tmp_path: Path) -> None:
    kit, key = _kit(tmp_path, screens.CLAUDE_APPROVAL_YES_NO)
    kit.supervisor.tick()
    kit.inspector.add_claude(4999, start_time=999)
    kit.terminal.set_foreground(CLAUDE, 4999)

    assert kit.supervisor.approve_pending() == {key: "process-identity-changed"}
    assert kit.sent == []


def test_a_shell_in_the_foreground_is_refused(tmp_path: Path) -> None:
    kit, key = _kit(tmp_path, screens.CLAUDE_APPROVAL_YES_NO)
    kit.supervisor.tick()
    kit.inspector.add_shell(5000)
    kit.terminal.set_foreground(CLAUDE, 5000)

    assert kit.supervisor.approve_pending() == {key: "process-identity-changed"}
    assert kit.sent == []


def test_an_unsafe_session_is_refused(tmp_path: Path) -> None:
    kit, key = _kit(tmp_path, screens.CLAUDE_APPROVAL_YES_NO)
    kit.supervisor.tick()
    kit.supervisor.mark_unsafe(key, "test")
    # An unsafe session keeps its last evidence; the gate still refuses it.
    kit.supervisor.sessions[key].approval_exact = True

    # Not even offered, so no refusal is logged on every scan.
    for _ in range(3):
        assert _scan(kit) == {}
    assert "approval_refused" not in _log(tmp_path)
    # A direct call still meets the gate's own refusal.
    assert kit.supervisor.approve(key, kit.supervisor.sessions[key].approval_fingerprint) == (
        "session-unsafe"
    )
    assert kit.sent == []


def test_a_codex_session_is_never_answered(tmp_path: Path) -> None:
    kit, _ = _kit(tmp_path, screens.CLAUDE_IDLE_COMPOSER)
    info = kit.inspector.add_codex(4202)
    ref = kit.terminal.add(
        CODEX, shell_pid=200, foreground_pid=4202, screen=list(screens.CODEX_ACTIVE)
    )
    kit.supervisor.select(ref, info.identity, "codex", "web : codex")
    kit.supervisor.tick()

    assert kit.supervisor.approve(ref.key(), "0123456789ab") == "unsupported-provider"
    assert kit.supervisor.approve("/nowhere", "0123456789ab") == "no-session"
    assert kit.sent == []


def test_a_failed_send_is_reported_and_not_remembered(tmp_path: Path) -> None:
    kit, key = _kit(tmp_path, screens.CLAUDE_APPROVAL_YES_NO)
    kit.terminal.send_fails = True

    assert _scan(kit) == {key: "send-failed:TerminalUnavailableError"}
    assert kit.supervisor.sessions[key].approved_fingerprint == ""


def test_an_approved_session_moves_on_to_working(tmp_path: Path) -> None:
    kit, key = _kit(tmp_path, screens.CLAUDE_APPROVAL_YES_NO)
    _scan(kit)
    kit.terminal.set_screen(CLAUDE, list(screens.CLAUDE_IDLE_COMPOSER))
    kit.supervisor.tick()

    session = kit.supervisor.sessions[key]
    assert session.state is SessionState.ACTIVE
    assert session.approved_fingerprint == ""


def test_a_failed_read_does_not_rearm_an_answered_box(tmp_path: Path) -> None:
    """Only a successful read without the prompt may clear the answered box.

    A D-Bus hiccup reads as an empty screen. Treating that as "the prompt is
    gone" re-armed the guard, and the next scan sent a second Enter onto the
    same, unchanged box.
    """
    kit, key = _kit(tmp_path, screens.CLAUDE_APPROVAL_YES_NO)
    assert _scan(kit) == {key: "approved"}
    read = kit.terminal.read_visible_text

    def hiccup(*args, **kwargs):
        raise TerminalUnavailableError("read failed")

    kit.terminal.read_visible_text = hiccup
    kit.supervisor.tick()
    kit.terminal.read_visible_text = read

    assert _scan(kit) == {}
    assert kit.sent == [(CLAUDE, "\r")]
    assert kit.supervisor.sessions[key].approved_fingerprint
