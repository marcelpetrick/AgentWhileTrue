# SPDX-FileCopyrightText: 2026 Marcel Petrick
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The y key: an auto-yes toggle that is visible, off at start, and gated like input."""

from __future__ import annotations

import io
import os
from datetime import UTC, datetime
from pathlib import Path

import pytest

from agent_while_true import cli
from agent_while_true.config import Config, Mode
from agent_while_true.lock import SingleInstanceLock
from agent_while_true.tui import DashboardState
from agent_while_true.ui import render_status, toggles_line
from tests import harness as harness_module
from tests import screens
from tests.pty_dashboard import Dashboard

CLAUDE = "/Sessions/1"


class InteractiveOutput(io.StringIO):
    def isatty(self) -> bool:
        return True


def _kit(tmp_path: Path, mode: Mode, screen: list[str]):
    kit = harness_module.build(tmp_path, mode=mode)
    info = kit.inspector.add_claude(4101)
    ref = kit.terminal.add(CLAUDE, shell_pid=100, foreground_pid=4101, screen=list(screen))
    kit.supervisor.select(ref, info.identity, "claude", "api : claude")
    return kit


def _run(tmp_path, monkeypatch, kit, keys: list[str], *, hold_lock: bool) -> str:
    pressed = iter(keys)
    size = os.terminal_size((120, 40))
    monkeypatch.setattr(cli.shutil, "get_terminal_size", lambda fallback=None: size)
    monkeypatch.setattr(cli.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(cli.TerminalKeys, "read", lambda self, timeout: next(pressed))
    monkeypatch.setattr(cli.HealthMonitor, "start", lambda self: None)
    stream = InteractiveOutput()
    flag = "--auto" if kit.supervisor.config.mode is Mode.AUTO else "--observe"
    args = cli.build_parser().parse_args(["run", flag, "--no-color"])
    lock = SingleInstanceLock.in_directory(tmp_path / "runtime")
    if hold_lock:
        lock.acquire()
    assert cli._loop(kit.supervisor, kit.supervisor.config, args, stream, lock) == cli.EXIT_OK
    return stream.getvalue()


@pytest.mark.parametrize("key", ["y", "Y"])
def test_y_toggles_auto_yes_and_reports_each_switch(key: str) -> None:
    dashboard = DashboardState.from_interval(1.0)
    assert dashboard.auto_yes is False

    dashboard.handle(key)
    assert dashboard.auto_yes is True
    assert dashboard.consume_auto_yes_toggle() is True
    assert dashboard.consume_auto_yes_toggle() is False

    dashboard.handle(key)
    assert dashboard.auto_yes is False


def test_the_toggle_line_says_what_auto_yes_will_do() -> None:
    auto, observe = Config(mode=Mode.AUTO), Config(mode=Mode.OBSERVE)

    assert "auto-yes on permission prompts: OFF" in toggles_line([], auto, auto_yes=False)
    assert "ON - approves any command asked" in toggles_line([], auto, auto_yes=True)
    assert "ON, inert: observe mode sends nothing" in toggles_line([], observe, auto_yes=True)
    ask = Config(mode=Mode.ASK)
    assert "ON, inert: ask mode confirms each action" in toggles_line([], ask, auto_yes=True)


@pytest.mark.parametrize(
    ("config", "shown"),
    [
        (Config(mode=Mode.OBSERVE), "[A] auto-resume on limit: OFF"),
        (Config(mode=Mode.ASK), "[A] auto-resume on limit: ASK each"),
        (Config(mode=Mode.AUTO), "[A] auto-resume on limit: ON (Claude)"),
    ],
    ids=["observe", "ask", "auto"],
)
def test_both_switches_are_shown_side_by_side(config: Config, shown: str) -> None:
    line = toggles_line([], config, auto_yes=False)

    assert line.startswith(shown)
    assert "[y] auto-yes on permission prompts: OFF" in line


def test_the_dashboard_shows_the_toggle_its_key_and_its_help(tmp_path: Path) -> None:
    kit = _kit(tmp_path, Mode.AUTO, screens.CLAUDE_APPROVAL_YES_NO)
    kit.supervisor.tick()
    frame = render_status(
        kit.supervisor.sessions.values(),
        now=datetime.now(UTC),
        config=kit.supervisor.config,
        show_help=True,
        width=200,
    )

    assert "[y] auto-yes on permission prompts: OFF   waiting for approval: 1" in frame
    assert "y auto-yes" in frame
    assert "y       toggle auto-yes" in frame
    assert "APPROVAL_PENDING" in frame


def test_pressing_y_answers_the_waiting_prompt(tmp_path: Path, monkeypatch) -> None:
    kit = _kit(tmp_path, Mode.AUTO, screens.CLAUDE_APPROVAL_YES_NO)

    output = _run(tmp_path, monkeypatch, kit, ["y", "", "q"], hold_lock=True)

    assert kit.sent == [(CLAUDE, "\r")]
    # The switch rescans at once, so the approval summary is what is drawn.
    assert "auto-yes approved 1/1 permission prompt(s)" in output
    log = (tmp_path / "agent-while-true.log").read_text(encoding="utf-8")
    assert "auto_yes_toggled enabled=true" in log.lower()
    assert "approval_sent" in log
    assert "ON - approves any command asked" in output


def test_without_the_key_nothing_is_approved(tmp_path: Path, monkeypatch) -> None:
    kit = _kit(tmp_path, Mode.AUTO, screens.CLAUDE_APPROVAL_YES_NO)

    output = _run(tmp_path, monkeypatch, kit, ["", "", "q"], hold_lock=True)

    assert kit.sent == []
    assert "auto-yes on permission prompts: OFF" in output


def test_pressing_y_twice_switches_it_off_again(tmp_path: Path, monkeypatch) -> None:
    kit = _kit(tmp_path, Mode.AUTO, screens.CLAUDE_IDLE_COMPOSER)

    output = _run(tmp_path, monkeypatch, kit, ["y", "y", "", "q"], hold_lock=True)

    assert "auto-yes off: permission prompts wait for you" in output
    kit.terminal.set_screen(CLAUDE, list(screens.CLAUDE_APPROVAL_YES_NO))
    assert kit.sent == []


def test_without_input_control_auto_yes_stays_inert(tmp_path: Path, monkeypatch) -> None:
    kit = _kit(tmp_path, Mode.OBSERVE, screens.CLAUDE_APPROVAL_YES_NO)

    output = _run(tmp_path, monkeypatch, kit, ["y", "", "q"], hold_lock=False)

    assert kit.sent == []
    assert "auto-yes on, but observe mode sends nothing" in output
    assert "ON, inert: observe mode sends nothing" in output


@pytest.mark.e2e
def test_the_real_dashboard_toggles_auto_yes_with_y(tmp_path: Path) -> None:
    """The real CLI on a pseudo-terminal, offline and without Konsole.

    A frame reaches the pseudo-terminal in chunks, so each step waits for the
    very rows it asserts - the header and the last-event row - rather than for
    one and then reading the other before it has arrived.
    """
    dashboard = Dashboard(tmp_path)
    dashboard.read_until(
        lambda text: (
            "auto-yes on permission prompts: OFF" in text
            and "[A] auto-resume on limit: OFF" in text
        )
    )

    start = len(dashboard.text)
    dashboard.press("y")
    dashboard.read_until(
        lambda text: (
            "ON, inert: observe mode sends nothing" in text[start:]
            and "auto-yes on, but observe mode sends nothing" in text[start:]
        )
    )

    start = len(dashboard.text)
    dashboard.press("y")
    dashboard.read_until(
        lambda text: (
            "auto-yes on permission prompts: OFF" in text[start:]
            and "auto-yes off: permission prompts wait for you" in text[start:]
        )
    )
    assert dashboard.quit() == 0
