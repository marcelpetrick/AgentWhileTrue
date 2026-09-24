# SPDX-FileCopyrightText: 2026 Marcel Petrick
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""A whip crack reaches only a revalidated, idle, empty provider composer."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from agent_while_true.config import Mode
from agent_while_true.fsm import whip_keystrokes
from agent_while_true.providers.base import BRACKETED_PASTE_END, BRACKETED_PASTE_START
from agent_while_true.quota import Availability
from agent_while_true.states import ActionState
from agent_while_true.whip import PHRASES, message
from tests import harness as harness_module
from tests import screens

CLAUDE = "/Sessions/1"
CODEX = "/Sessions/2"
TEXT = message(0)


def _kit(tmp_path: Path, *, mode: Mode = Mode.AUTO, claude=None, codex=None):
    kit = harness_module.build(tmp_path, mode=mode)
    claude_info = kit.inspector.add_claude(4101)
    codex_info = kit.inspector.add_codex(4202)
    claude_ref = kit.terminal.add(
        CLAUDE,
        shell_pid=100,
        foreground_pid=4101,
        screen=list(claude or screens.CLAUDE_IDLE_COMPOSER),
        title="api : claude",
    )
    codex_ref = kit.terminal.add(
        CODEX,
        shell_pid=200,
        foreground_pid=4202,
        screen=list(codex or screens.CODEX_ACTIVE),
        title="web : codex",
    )
    kit.supervisor.select(claude_ref, claude_info.identity, "claude", "api : claude")
    kit.supervisor.select(codex_ref, codex_info.identity, "codex", "web : codex")
    return kit, claude_ref.key(), codex_ref.key()


def _messages():
    """Every phrase once, in order, the way a crack offers them."""
    return ((phrase, message(phrase)) for phrase in range(len(PHRASES)))


def _whip(kit, messages=None) -> dict[str, str]:
    outcomes = kit.supervisor.whip(_messages() if messages is None else messages)
    return {key: outcome.reason for key, outcome in outcomes.items()}


def _log(tmp_path: Path) -> str:
    return (tmp_path / "agent-while-true.log").read_text(encoding="utf-8")


def test_both_idle_composers_receive_the_reminder_as_one_paste(tmp_path: Path) -> None:
    kit, claude, codex = _kit(tmp_path)

    outcomes = kit.supervisor.whip(_messages())

    assert {key: outcome.phrase for key, outcome in outcomes.items()} == {claude: 0, codex: 1}
    assert all(outcome.delivered for outcome in outcomes.values())
    keystrokes = f"{BRACKETED_PASTE_START}{TEXT}{BRACKETED_PASTE_END}\r"
    assert whip_keystrokes(TEXT) == keystrokes
    assert kit.sent == [(CLAUDE, keystrokes), (CODEX, whip_keystrokes(message(1)))]
    log = _log(tmp_path)
    assert log.count("whip_delivered") == 2
    assert "phrase=0" in log
    assert TEXT not in log


def test_observe_mode_never_types_a_reminder(tmp_path: Path) -> None:
    kit, claude, codex = _kit(tmp_path, mode=Mode.OBSERVE)

    assert _whip(kit) == {claude: "observe-mode", codex: "observe-mode"}
    assert kit.sent == []
    assert _log(tmp_path).count("whip_skipped") == 2


def test_ask_mode_types_because_the_keypress_is_the_confirmation(tmp_path: Path) -> None:
    kit, claude, _ = _kit(tmp_path, mode=Mode.ASK)
    assert _whip(kit)[claude] == "delivered"


@pytest.mark.parametrize(
    ("claude_screen", "codex_screen", "reason"),
    [
        (screens.CLAUDE_DRAFT, screens.CODEX_DRAFT, "composer-not-empty"),
        (
            screens.CLAUDE_DRAFT_AFTER_NEWLINE,
            screens.CODEX_DRAFT_AFTER_NEWLINE,
            "composer-not-empty",
        ),
        (screens.CLAUDE_SESSION_LIMIT, screens.CODEX_USAGE_LIMIT, "prompt-on-screen"),
        (screens.CLAUDE_LIMIT_MENU, screens.CODEX_OUT_OF_CREDITS, "prompt-on-screen"),
        (screens.CLAUDE_SELF_HEALING, screens.CODEX_APPROACHING, "prompt-on-screen"),
        (["  still thinking"], ["• Working"], "composer-not-empty"),
    ],
)
def test_anything_but_an_empty_working_composer_is_skipped(
    tmp_path: Path, claude_screen: list[str], codex_screen: list[str], reason: str
) -> None:
    kit, claude, codex = _kit(tmp_path, claude=claude_screen, codex=codex_screen)

    assert _whip(kit) == {claude: reason, codex: reason}
    assert kit.sent == []


def test_a_shell_in_the_foreground_is_never_whipped(tmp_path: Path) -> None:
    kit, claude, codex = _kit(tmp_path)
    kit.inspector.add_shell(5000, tty="pts/3")
    kit.terminal.set_foreground(CLAUDE, 5000)
    kit.terminal.close(CODEX)

    results = _whip(kit)

    assert results == {claude: "process-identity-changed", codex: "process-identity-changed"}
    assert kit.sent == []


def test_a_process_under_a_multiplexer_is_not_automatable(tmp_path: Path) -> None:
    kit, claude, _ = _kit(tmp_path)
    info = kit.inspector.processes[4101]
    kit.inspector.processes[4101] = replace(info, environ_keys=frozenset({"HOME", "TMUX"}))

    assert _whip(kit)[claude].startswith("not-automatable:")
    assert (CLAUDE, whip_keystrokes(TEXT)) not in kit.sent


def test_a_process_swapped_after_the_screen_read_is_caught_last(tmp_path: Path) -> None:
    """The final read before sendText is the foreground process itself."""
    kit, claude, codex = _kit(tmp_path)
    kit.inspector.add_shell(5000, tty="pts/3")

    def shell_takes_over(session_id: str) -> None:
        if session_id == CLAUDE:
            kit.terminal.set_foreground(CLAUDE, 5000)

    kit.terminal.after_read = shell_takes_over
    results = _whip(kit)

    assert results[claude] == "process-identity-changed"
    assert results[codex] == "delivered"
    assert [session for session, _ in kit.sent] == [CODEX]


def test_unsafe_sessions_and_pending_resumes_are_left_alone(tmp_path: Path) -> None:
    kit, claude, codex = _kit(tmp_path)
    kit.supervisor.mark_unsafe(claude, "operator")
    kit.supervisor.store.plan("resume-1", provider="codex", session=codex, process="p")
    kit.supervisor.sessions[codex].pending_key = "resume-1"

    assert _whip(kit) == {
        claude: "session-unsafe",
        codex: "action-in-flight",
    }
    assert kit.sent == []


@pytest.mark.parametrize("text", ["", "line\nbreak", "esc\x1b[31m", "café"])
def test_only_printable_ascii_text_is_ever_typed(tmp_path: Path, text: str) -> None:
    kit, claude, codex = _kit(tmp_path)
    assert _whip(kit, iter([(7, text), (7, text)])) == {claude: "unsafe-text", codex: "unsafe-text"}
    assert kit.sent == []


def test_a_failed_send_is_reported_and_not_retried(tmp_path: Path) -> None:
    kit, claude, codex = _kit(tmp_path)
    kit.terminal.send_fails = True

    results = _whip(kit)

    assert results == {
        claude: "send-failed:TerminalUnavailableError",
        codex: "send-failed:TerminalUnavailableError",
    }
    assert kit.sent == []
    assert kit.supervisor.store.records == {}


def test_unselected_konsole_sessions_never_hear_the_whip(tmp_path: Path) -> None:
    kit, claude, codex = _kit(tmp_path)
    stranger = kit.inspector.add_claude(4303, start_time=999, tty="pts/9")
    kit.terminal.add(
        "/Sessions/3",
        shell_pid=300,
        foreground_pid=stranger.identity.pid,
        screen=list(screens.CLAUDE_IDLE_COMPOSER),
    )

    assert set(_whip(kit)) == {claude, codex}
    assert "/Sessions/3" not in {session for session, _ in kit.sent}


@pytest.mark.parametrize("state", [ActionState.PLANNED, ActionState.SENT])
def test_an_unsettled_persisted_resume_blocks_the_whip(tmp_path: Path, state: ActionState) -> None:
    kit, claude, _ = _kit(tmp_path)
    session = kit.supervisor.sessions[claude]
    kit.supervisor.store.plan("resume-1", provider="claude", session=claude, process="p")
    kit.supervisor.store.mark("resume-1", state)
    session.pending_key = "resume-1"

    assert _whip(kit)[claude] == "action-in-flight"


@pytest.mark.parametrize("state", [ActionState.FAILED, ActionState.VERIFIED])
def test_a_settled_resume_leaves_no_permanent_whip_veto(tmp_path: Path, state: ActionState) -> None:
    """``pending_key`` survives a failed attempt; only an unsettled record blocks."""
    kit, claude, _ = _kit(tmp_path)
    session = kit.supervisor.sessions[claude]
    kit.supervisor.store.plan("resume-1", provider="claude", session=claude, process="p")
    kit.supervisor.store.mark("resume-1", state, result="still-blocked")
    session.pending_key = "resume-1"

    assert _whip(kit)[claude] == "delivered"


def test_a_resume_awaiting_verification_blocks_the_whip(tmp_path: Path) -> None:
    kit, claude, _ = _kit(tmp_path)
    kit.supervisor.sessions[claude].verify_after = kit.clock.wall

    assert _whip(kit)[claude] == "action-in-flight"


def test_an_exhausted_quota_is_not_whipped_into_a_fresh_limit(tmp_path: Path) -> None:
    """A limit banner scrolled out of view does not make the quota available.

    Submitting a turn there could only come back as a new limit prompt, which
    burns exactly what the whip complains about.
    """
    kit, claude, codex = _kit(tmp_path)
    kit.quota["claude"].availability = Availability.EXHAUSTED

    assert _whip(kit) == {claude: "quota-exhausted", codex: "delivered"}
    assert [session for session, _ in kit.sent] == [CODEX]


def test_unknown_quota_does_not_block_a_reminder(tmp_path: Path) -> None:
    """Unknown quota authorises no resume, but a reminder is not a resume."""
    kit, claude, _ = _kit(tmp_path)
    kit.quota["claude"].availability = Availability.UNKNOWN

    assert _whip(kit)[claude] == "delivered"


def test_each_session_gets_its_own_reminder_and_skips_spend_none(tmp_path: Path) -> None:
    """A skipped session does not use up a phrase, so the next one gets it."""
    kit, claude, codex = _kit(tmp_path, claude=screens.CLAUDE_DRAFT)

    outcomes = kit.supervisor.whip(_messages())

    assert outcomes[claude].reason == "composer-not-empty"
    assert outcomes[claude].phrase is None
    assert outcomes[codex].phrase == 0
    assert kit.sent == [(CODEX, whip_keystrokes(message(0)))]


def test_a_crack_that_runs_out_of_messages_types_nothing_more(tmp_path: Path) -> None:
    kit, claude, codex = _kit(tmp_path)

    assert _whip(kit, iter([(3, message(3))])) == {
        claude: "delivered",
        codex: "no-message-left",
    }
    assert kit.sent == [(CLAUDE, whip_keystrokes(message(3)))]
