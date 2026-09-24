# SPDX-FileCopyrightText: 2026 Marcel Petrick
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The dashboard's whip key: animation, counter, cooldown and delivery wiring."""

from __future__ import annotations

import io
import os
import random
from datetime import UTC, datetime
from pathlib import Path

import pytest

from agent_while_true import cli, whip
from agent_while_true.config import Config, Mode
from agent_while_true.lock import SingleInstanceLock
from agent_while_true.tui import DashboardState
from agent_while_true.ui import render_status
from tests import harness as harness_module
from tests import screens


class InteractiveOutput(io.StringIO):
    def isatty(self) -> bool:
        return True


def _kit(tmp_path: Path, mode: Mode = Mode.AUTO):
    kit = harness_module.build(tmp_path, mode=mode)
    info = kit.inspector.add_claude(4101)
    ref = kit.terminal.add(
        "/Sessions/1", shell_pid=100, foreground_pid=4101, screen=list(screens.CLAUDE_ACTIVE)
    )
    kit.supervisor.select(ref, info.identity, "claude", "api : claude")
    return kit


@pytest.fixture(autouse=True)
def _small_screen(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        cli.shutil, "get_terminal_size", lambda fallback=None: os.terminal_size((80, 24))
    )


@pytest.mark.parametrize("key", ["w", "W"])
def test_w_requests_exactly_one_crack(key: str) -> None:
    state = DashboardState.from_interval(2)
    assert state.handle(key) is False
    assert state.consume_whip()
    assert not state.consume_whip()


def test_dashboard_shows_the_counter_the_key_and_its_help() -> None:
    now = datetime(2026, 9, 24, 12, tzinfo=UTC)
    text = render_status(
        [], now=now, config=Config(), show_help=True, whip_badge="whip=2 crack(s)/1 delivered"
    )
    assert "whip=2 crack(s)/1 delivered" in text
    assert "w whip" in text
    assert "crack the whip" in text
    assert "whip=" not in render_status([], now=now, config=Config())


def test_an_armed_crack_animates_then_delivers(tmp_path: Path) -> None:
    kit = _kit(tmp_path)
    lock = SingleInstanceLock.in_directory(tmp_path / "runtime")
    lock.acquire()
    counter = whip.WhipCounter(rng=random.Random(5))
    stream = io.StringIO()
    try:
        note = cli._crack_whip(kit.supervisor, lock, counter, stream, sleep=lambda _: None)
    finally:
        lock.release()

    assert "[###]" in stream.getvalue()
    assert "CRACK" in stream.getvalue() or "____" in stream.getvalue()
    assert note.startswith('whip cracked: "')
    assert note.endswith("reached 1/1")
    assert len(kit.sent) == 1
    assert counter.cracks == 1
    assert counter.delivered == 1


def test_skipped_sessions_are_summarised_by_reason(tmp_path: Path) -> None:
    kit = _kit(tmp_path)
    kit.terminal.set_screen("/Sessions/1", list(screens.CLAUDE_DRAFT))
    lock = SingleInstanceLock.in_directory(tmp_path / "runtime")
    lock.acquire()
    try:
        note = cli._crack_whip(
            kit.supervisor, lock, whip.WhipCounter(), io.StringIO(), sleep=lambda _: None
        )
    finally:
        lock.release()
    assert note.endswith("reached 0/1; skipped 1x composer-not-empty")
    assert kit.sent == []


def test_without_input_control_the_whip_only_cracks_in_the_air(tmp_path: Path) -> None:
    kit = _kit(tmp_path, mode=Mode.OBSERVE)
    lock = SingleInstanceLock.in_directory(tmp_path / "runtime")
    counter = whip.WhipCounter()

    note = cli._crack_whip(kit.supervisor, lock, counter, io.StringIO(), sleep=lambda _: None)

    assert "observe mode sends nothing" in note
    assert kit.sent == []
    assert counter.cracks == 1
    assert counter.delivered == 0


def test_the_fourth_crack_in_a_minute_is_refused_without_animation(tmp_path: Path) -> None:
    kit = _kit(tmp_path, mode=Mode.OBSERVE)
    lock = SingleInstanceLock.in_directory(tmp_path / "runtime")
    counter = whip.WhipCounter()
    for _ in range(3):
        cli._crack_whip(kit.supervisor, lock, counter, io.StringIO(), sleep=lambda _: None)
    stream = io.StringIO()

    note = cli._crack_whip(kit.supervisor, lock, counter, stream, sleep=lambda _: None)

    assert note.startswith("whip cooling down for ")
    assert stream.getvalue() == ""
    assert counter.cracks == 3


def test_pressing_w_in_the_dashboard_cracks_and_counts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    kit = _kit(tmp_path, mode=Mode.OBSERVE)
    pressed = iter(["w", "", "q"])
    monkeypatch.setattr(cli.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(cli.TerminalKeys, "read", lambda self, timeout: next(pressed))
    monkeypatch.setattr(cli.HealthMonitor, "start", lambda self: None)
    monkeypatch.setattr(whip, "FRAME_SECONDS", 0.0)
    stream = InteractiveOutput()
    args = cli.build_parser().parse_args(["run", "--observe", "--no-color"])
    lock = SingleInstanceLock.in_directory(tmp_path / "runtime")

    assert cli._loop(kit.supervisor, kit.supervisor.config, args, stream, lock) == cli.EXIT_OK

    output = stream.getvalue()
    assert "[###]" in output
    assert "whip=0 crack(s)/0 delivered" in output
    assert "whip=1 crack(s)/0 delivered" in output
    assert "whip cracked in the air" in output
    assert kit.sent == []
