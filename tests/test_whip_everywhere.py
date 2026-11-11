# SPDX-FileCopyrightText: 2026 Marcel Petrick
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The whip reaches every agent tab: busy tabs later, unwatched tabs too.

Maintainer request 2026-11-11: a crack is received everywhere, including tabs
with a draft, tabs not selected in the dashboard and Claude sessions running
background agents. The draft is never typed into: the reminder waits in memory
until the input box is free, through the full revalidating gate.
"""

import io
import re
from pathlib import Path

import pytest

from agent_while_true import cli, whip
from agent_while_true.config import Mode
from agent_while_true.fsm import WHIP_BACKGROUND_SUFFIX, WHIP_QUEUE_SECONDS, whip_keystrokes
from agent_while_true.lock import SingleInstanceLock
from agent_while_true.whip import PHRASES, message
from tests import harness as harness_module
from tests import screens
from tests.pty_dashboard import Dashboard

TAB = "/Sessions/1"
OTHER = "/Sessions/7"


def _kit(tmp_path: Path, screen=None, *, mode: Mode = Mode.AUTO):
    kit = harness_module.build(tmp_path, mode=mode)
    info = kit.inspector.add_claude(4101)
    ref = kit.terminal.add(
        TAB, shell_pid=100, foreground_pid=4101, screen=list(screen or screens.CLAUDE_DRAFT)
    )
    kit.supervisor.select(ref, info.identity, "claude", "api : claude")
    return kit, ref.key()


def _messages():
    return ((phrase, message(phrase)) for phrase in range(len(PHRASES)))


def _log(tmp_path: Path) -> str:
    return (tmp_path / "agent-while-true.log").read_text(encoding="utf-8")


def test_a_draft_keeps_the_reminder_until_the_input_box_is_free(tmp_path: Path) -> None:
    kit, key = _kit(tmp_path)

    assert kit.supervisor.whip(_messages())[key].reason == "queued:composer-not-empty"
    assert kit.sent == []
    for _ in range(3):  # still drafting: nothing typed, nothing logged again
        assert kit.supervisor.deliver_queued_whips() == {}
    assert kit.sent == []

    kit.terminal.set_screen(TAB, list(screens.CLAUDE_IDLE_COMPOSER))
    outcome = kit.supervisor.deliver_queued_whips()[key]

    assert outcome.delivered
    assert outcome.phrase == 0
    assert kit.sent == [(TAB, whip_keystrokes(message(0)))]
    assert kit.supervisor.whip_queue == {}
    assert kit.supervisor.deliver_queued_whips() == {}
    log = _log(tmp_path)
    assert log.count("event=whip_queued") == 1
    assert "reason=delivered-after-wait" in log
    assert message(0) not in log


@pytest.mark.parametrize(
    "screen",
    [screens.CLAUDE_SESSION_LIMIT, screens.CLAUDE_LIMIT_MENU, screens.CLAUDE_APPROVAL_YES_NO],
    ids=["limit", "wait-menu", "permission"],
)
def test_a_prompt_is_never_answered_by_a_waiting_reminder(tmp_path: Path, screen) -> None:
    kit, key = _kit(tmp_path, screen)

    assert kit.supervisor.whip(_messages())[key].reason == "queued:prompt-on-screen"
    assert kit.supervisor.deliver_queued_whips() == {}
    assert kit.sent == []


def test_a_waiting_reminder_expires(tmp_path: Path) -> None:
    kit, key = _kit(tmp_path)
    kit.supervisor.whip(_messages())
    kit.clock.advance(WHIP_QUEUE_SECONDS + 1)
    kit.terminal.set_screen(TAB, list(screens.CLAUDE_IDLE_COMPOSER))

    assert kit.supervisor.deliver_queued_whips()[key].reason == "queue-expired"
    assert kit.sent == []
    assert kit.supervisor.whip_queue == {}


def test_a_replacement_process_never_receives_a_waiting_reminder(tmp_path: Path) -> None:
    kit, key = _kit(tmp_path)
    kit.supervisor.whip(_messages())
    replacement = kit.inspector.add_claude(4999, start_time=777)
    kit.terminal.sessions[TAB].foreground_pid = replacement.identity.pid
    kit.terminal.set_screen(TAB, list(screens.CLAUDE_IDLE_COMPOSER))

    assert kit.supervisor.deliver_queued_whips()[key].reason == "process-identity-changed"
    assert kit.sent == []


def test_a_new_crack_replaces_the_waiting_reminder(tmp_path: Path) -> None:
    kit, _key = _kit(tmp_path)
    kit.supervisor.whip(iter([(3, message(3))]))
    kit.supervisor.whip(iter([(5, message(5))]))
    kit.terminal.set_screen(TAB, list(screens.CLAUDE_IDLE_COMPOSER))

    kit.supervisor.deliver_queued_whips()

    assert kit.sent == [(TAB, whip_keystrokes(message(5)))]


def test_losing_input_control_drops_waiting_reminders(tmp_path: Path) -> None:
    kit, _ = _kit(tmp_path)
    kit.supervisor.whip(_messages())
    lock = SingleInstanceLock.in_directory(tmp_path / "runtime")

    assert (
        cli._deliver_queued_whips(kit.supervisor, lock, whip.WhipCounter(), kit.supervisor.config)
        == ""
    )
    assert kit.supervisor.whip_queue == {}
    assert kit.sent == []


def test_unwatched_agent_tabs_hear_the_crack(tmp_path: Path) -> None:
    kit, _key = _kit(tmp_path, screens.CLAUDE_IDLE_COMPOSER)
    stranger = kit.inspector.add_codex(4303, start_time=999, tty="pts/9")
    kit.terminal.add(
        OTHER,
        shell_pid=300,
        foreground_pid=stranger.identity.pid,
        screen=list(screens.CODEX_ACTIVE),
    )
    shell = kit.inspector.add_shell(4404, tty="pts/10")
    kit.terminal.add("/Sessions/8", shell_pid=4404, foreground_pid=shell.pid, screen=["$ "])
    lock = SingleInstanceLock.in_directory(tmp_path / "runtime")
    lock.acquire()
    try:
        note = cli._crack_whip(
            kit.supervisor, lock, whip.WhipCounter(), io.StringIO(), sleep=lambda _: None
        )
    finally:
        lock.release()

    assert note.startswith("whip cracked: reached 2/2")
    assert {session for session, _ in kit.sent} == {TAB, OTHER}
    assert OTHER not in {session.ref.session_id for session in kit.supervisor.sessions.values()}


def test_claude_with_background_agents_is_asked_to_pass_it_on(tmp_path: Path) -> None:
    kit, key = _kit(tmp_path, screens.CLAUDE_2_1_292_AGENT_PANEL)

    assert kit.supervisor.whip(_messages())[key].delivered
    assert kit.sent == [(TAB, whip_keystrokes(message(0) + WHIP_BACKGROUND_SUFFIX))]


def test_without_background_agents_the_reminder_is_unchanged(tmp_path: Path) -> None:
    kit, _ = _kit(tmp_path, screens.CLAUDE_IDLE_COMPOSER)
    kit.supervisor.whip(_messages())

    assert kit.sent == [(TAB, whip_keystrokes(message(0)))]


def test_observe_mode_drops_a_waiting_reminder(tmp_path: Path) -> None:
    kit, key = _kit(tmp_path)
    kit.supervisor.whip(_messages())
    kit.supervisor.config = kit.supervisor.config.__class__(mode=Mode.OBSERVE)
    kit.terminal.set_screen(TAB, list(screens.CLAUDE_IDLE_COMPOSER))

    assert kit.supervisor.deliver_queued_whips()[key].reason == "observe-mode"
    assert kit.sent == []


def _flat(text: str) -> str:
    """The dashboard text without colours, box borders or wrapping."""
    plain = re.sub(r"\x1b\[[0-9;?]*[A-Za-z]", "", text)
    return " ".join(plain.replace("\u2502", " ").split())


@pytest.mark.e2e
def test_real_pty_reports_the_waiting_reminder_and_its_late_delivery(tmp_path: Path) -> None:
    dashboard = Dashboard(
        tmp_path, "--no-color", driver=Path(__file__).with_name("pty_whip_queue.py")
    )
    try:
        dashboard.read_until(lambda text: "whip=0 sent=0" in text)
        start = len(dashboard.text)
        dashboard.press("w")
        dashboard.read_until(
            lambda text: (
                "reached 1/2" in _flat(text[start:])
                and "1 waiting for a free input box (1x composer-not-empty)" in _flat(text[start:])
            ),
            timeout=20,
        )
        dashboard.read_until(
            lambda text: "whip reached 1 more tab once free" in _flat(text[start:]), timeout=20
        )
        dashboard.read_until(lambda text: "sent=2" in text[start:], timeout=20)
    finally:
        assert dashboard.quit() == 0
