# SPDX-FileCopyrightText: 2026 Marcel Petrick
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for interactive dashboard state without touching a real terminal."""

import pytest

from agent_watch import tui
from agent_watch.tui import INTERVALS, THEMES, DashboardState


@pytest.mark.parametrize("ready", [False, True])
def test_terminal_keys_restores_mode(monkeypatch, ready):
    restored = []
    monkeypatch.setattr(tui.sys.stdin, "fileno", lambda: 42)
    monkeypatch.setattr(tui.termios, "tcgetattr", lambda fd: ["original"])
    monkeypatch.setattr(tui.tty, "setcbreak", lambda fd: None)
    monkeypatch.setattr(tui.select, "select", lambda *args: ([42] if ready else [], [], []))
    monkeypatch.setattr(tui.os, "read", lambda *args: b"d")
    monkeypatch.setattr(tui.termios, "tcsetattr", lambda *args: restored.append(args))
    assert tui.TerminalKeys(True).read(0.5) == ("d" if ready else "")
    assert restored == [(42, tui.termios.TCSADRAIN, ["original"])]
    assert tui.TerminalKeys(False).read(0.5) == ""


def test_terminal_keys_restores_mode_on_read_error(monkeypatch):
    restored = []
    monkeypatch.setattr(tui.sys.stdin, "fileno", lambda: 42)
    monkeypatch.setattr(tui.termios, "tcgetattr", lambda fd: ["original"])
    monkeypatch.setattr(tui.tty, "setcbreak", lambda fd: None)
    monkeypatch.setattr(tui.select, "select", lambda *args: ([42], [], []))
    monkeypatch.setattr(tui.termios, "tcsetattr", lambda *args: restored.append(args))

    def fail(*args):
        raise OSError("terminal closed")

    monkeypatch.setattr(tui.os, "read", fail)
    with pytest.raises(OSError, match="terminal closed"):
        tui.TerminalKeys(True).read(0.5)
    assert restored == [(42, tui.termios.TCSADRAIN, ["original"])]


def test_refresh_keys_follow_btop_interval_direction() -> None:
    state = DashboardState.from_interval(2)
    state.handle("+")
    assert state.interval == 3
    state.handle("-")
    assert state.interval == 2


def test_dashboard_keys_toggle_state_and_quit() -> None:
    state = DashboardState.from_interval(1)
    assert not state.handle("p")
    assert state.paused
    state.handle("h")
    assert state.help_visible
    state.handle("r")
    assert state.rescan_requested
    state.handle("t")
    assert state.theme == "vivid"
    state.handle("e")
    assert not state.show_events
    state.handle("l")
    assert state.history_length == 20
    state.handle("a")
    assert not state.consume_mode_toggle()
    state.handle("A")
    assert state.consume_mode_toggle()
    assert not state.consume_mode_toggle()
    assert state.handle("q")


def test_detail_controls_do_not_toggle_input_mode() -> None:
    state = DashboardState.from_interval(2)
    state.handle("d")
    state.handle("]")
    assert state.details_visible
    assert state.detail_index == 1
    state.handle("[")
    assert state.detail_index == 0
    assert not state.consume_mode_toggle()


def test_viewport_controls_move_and_reset_scroll() -> None:
    state = DashboardState.from_interval(2)
    state.handle("j")
    state.handle("j")
    assert state.scroll_offset == 2
    state.handle("k")
    assert state.scroll_offset == 1
    state.handle("g")
    assert state.scroll_offset == 0
    state.handle("G")
    assert state.scroll_offset > 1000
    state.handle("d")
    assert state.scroll_offset == 0
    state.handle("j")
    state.handle("]")
    assert state.scroll_offset == 0


def test_refresh_ladder_clamps_at_both_ends() -> None:
    state = DashboardState.from_interval(INTERVALS[0])
    state.handle("-")
    assert state.interval == INTERVALS[0]
    state.interval_index = len(INTERVALS) - 1
    state.handle("+")
    assert state.interval == INTERVALS[-1]


def test_dashboard_cycles_all_five_themes() -> None:
    state = DashboardState.from_interval(2)
    visited = [state.theme]
    for _ in range(len(THEMES) - 1):
        state.handle("t")
        visited.append(state.theme)
    assert visited == ["dark", "vivid", "cga", "amber", "plain"]
    state.handle("t")
    assert state.theme == "dark"
