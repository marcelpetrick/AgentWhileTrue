# SPDX-FileCopyrightText: 2026 Marcel Petrick
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""All-time whip counts at the service level: persisted, counts only, one writer."""

import io
import json
import random
from datetime import UTC, datetime
from pathlib import Path

import pytest

from agent_while_true import cli, whip
from agent_while_true.config import Mode
from agent_while_true.lock import SingleInstanceLock
from agent_while_true.summary import render_summary
from tests import harness as harness_module
from tests import screens
from tests.pty_dashboard import Dashboard


def _kit(tmp_path: Path, screen: list[str] | None = None, mode: Mode = Mode.AUTO):
    kit = harness_module.build(tmp_path, mode=mode)
    info = kit.inspector.add_claude(4101)
    ref = kit.terminal.add(
        "/Sessions/1",
        shell_pid=100,
        foreground_pid=4101,
        screen=list(screen or screens.CLAUDE_IDLE_COMPOSER),
    )
    kit.supervisor.select(ref, info.identity, "claude", "api : claude")
    return kit


def _counter(path: Path) -> whip.WhipCounter:
    return whip.WhipCounter(rng=random.Random(3), totals=whip.WhipTotals.load(path))


def _crack(kit, counter: whip.WhipCounter, tmp_path: Path, *, held: bool = True, **kwargs) -> str:
    lock = SingleInstanceLock.in_directory(tmp_path / "runtime")
    if held:
        lock.acquire()
    try:
        return cli._crack_whip(
            kit.supervisor, lock, counter, io.StringIO(), sleep=lambda _: None, **kwargs
        )
    finally:
        if held:
            lock.release()


def test_a_delivered_crack_is_counted_on_disk_and_survives_a_restart(tmp_path: Path) -> None:
    path = tmp_path / whip.TOTALS_FILENAME
    kit = _kit(tmp_path)
    _crack(kit, _counter(path), tmp_path)

    assert json.loads(path.read_text()) == {"cracks": 1, "delivered": 1, "version": 1}
    assert path.stat().st_mode & 0o777 == 0o600
    # A restarted service starts its run counts at zero but keeps the totals.
    restarted = _counter(path)
    assert (restarted.cracks, restarted.delivered) == (0, 0)
    assert restarted.badge(0.0) == "whip=0 sent=0 all-time 1/1"
    _crack(_kit(tmp_path / "again"), restarted, tmp_path)
    assert json.loads(path.read_text())["cracks"] == 2


def test_a_queued_reminder_is_counted_once_it_is_delivered(tmp_path: Path) -> None:
    path = tmp_path / whip.TOTALS_FILENAME
    kit = _kit(tmp_path, screens.CLAUDE_DRAFT)
    counter = _counter(path)
    _crack(kit, counter, tmp_path)
    assert json.loads(path.read_text()) == {"cracks": 1, "delivered": 0, "version": 1}

    kit.terminal.set_screen("/Sessions/1", list(screens.CLAUDE_IDLE_COMPOSER))
    lock = SingleInstanceLock.in_directory(tmp_path / "runtime")
    lock.acquire()
    try:
        note = cli._deliver_queued_whips(kit.supervisor, lock, counter, kit.supervisor.config)
        # Nothing left to deliver: no write for nothing.
        mtime = path.stat().st_mtime_ns
        cli._deliver_queued_whips(kit.supervisor, lock, counter, kit.supervisor.config)
        assert path.stat().st_mtime_ns == mtime
    finally:
        lock.release()
    assert "once free" in note
    assert json.loads(path.read_text())["delivered"] == 1


@pytest.mark.parametrize("paused", [True, False])
def test_a_crack_without_input_control_or_while_paused_is_not_counted(
    tmp_path: Path, paused: bool
) -> None:
    """Only the watcher that can type keeps the service-level counts."""
    path = tmp_path / whip.TOTALS_FILENAME
    kit = _kit(tmp_path, mode=Mode.AUTO if paused else Mode.OBSERVE)
    counter = _counter(path)
    _crack(kit, counter, tmp_path, held=paused, paused=paused)
    assert counter.cracks == 1  # the run counter still shows the crack
    assert not path.exists()


def test_another_watchers_additions_are_kept(tmp_path: Path) -> None:
    path = tmp_path / whip.TOTALS_FILENAME
    first = whip.WhipTotals.load(path)
    second = whip.WhipTotals.load(path)
    first.add(cracks=2, delivered=5)
    second.add(cracks=1, delivered=1)  # re-reads before adding
    assert (second.cracks, second.delivered) == (3, 6)
    second.add()  # nothing to add, nothing written
    assert json.loads(path.read_text())["cracks"] == 3


@pytest.mark.parametrize(
    "content",
    [
        "not json",
        "[]",
        '{"version": 2, "cracks": 4, "delivered": 4}',
        '{"version": 1, "cracks": -1, "delivered": 4}',
        '{"version": 1, "cracks": true, "delivered": 4}',
        '{"version": 1, "cracks": "4", "delivered": 4}',
    ],
)
def test_a_malformed_totals_file_counts_as_zero(tmp_path: Path, content: str) -> None:
    path = tmp_path / whip.TOTALS_FILENAME
    path.write_text(content)
    totals = whip.WhipTotals.load(path)
    assert (totals.cracks, totals.delivered) == (0, 0)
    assert whip.WhipCounter(totals=totals).badge(0.0) == "whip=0 sent=0"


def test_an_unwritable_totals_file_keeps_counting_in_memory(tmp_path: Path) -> None:
    blocked = tmp_path / "file"
    blocked.write_text("")
    totals = whip.WhipTotals(path=blocked / whip.TOTALS_FILENAME)
    totals.add(cracks=1, delivered=2)
    totals.add(cracks=1)
    assert (totals.cracks, totals.delivered) == (2, 2)
    assert not list(tmp_path.glob(".whip.json.*"))


def test_a_failed_write_is_saved_by_the_next_successful_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / whip.TOTALS_FILENAME
    totals = whip.WhipTotals.load(path)
    totals.add(cracks=1, delivered=1)
    real = Path.replace

    def failing(self: Path, target: Path) -> Path:
        raise OSError("disk full")

    monkeypatch.setattr(Path, "replace", failing)
    totals.add(cracks=1, delivered=3)
    assert json.loads(path.read_text()) == {"cracks": 1, "delivered": 1, "version": 1}
    monkeypatch.setattr(Path, "replace", real)
    totals.add(delivered=1)
    assert json.loads(path.read_text()) == {"cracks": 2, "delivered": 5, "version": 1}


def test_a_reading_watcher_shows_the_writers_new_counts(tmp_path: Path) -> None:
    path = tmp_path / whip.TOTALS_FILENAME
    observer = whip.WhipCounter(totals=whip.WhipTotals.load(path))
    assert observer.badge(0.0) == "whip=0 sent=0"
    whip.WhipTotals.load(path).add(cracks=3, delivered=8)
    assert observer.badge(0.0) == "whip=0 sent=0 all-time 3/8"
    path.unlink()  # a vanished file keeps the last counts on screen
    assert observer.badge(0.0) == "whip=0 sent=0 all-time 3/8"


def test_the_summary_reports_the_all_time_counts(tmp_path: Path) -> None:
    path = tmp_path / whip.TOTALS_FILENAME
    whip.WhipTotals.load(path).add(cracks=4, delivered=11)
    text = render_summary(
        tmp_path / "missing.log", now=datetime(2026, 11, 24, tzinfo=UTC), days=1, whip_totals=path
    )
    assert "Whip all time: cracks=4 reminders=11" in text
    assert "Whip all time" not in render_summary(
        tmp_path / "missing.log", now=datetime(2026, 11, 24, tzinfo=UTC), days=1
    )


@pytest.mark.e2e
def test_the_real_dashboard_shows_the_saved_all_time_counts(tmp_path: Path) -> None:
    state = tmp_path / "state" / "agent-while-true"
    state.mkdir(parents=True)
    (state / whip.TOTALS_FILENAME).write_text('{"version": 1, "cracks": 7, "delivered": 21}')
    dashboard = Dashboard(tmp_path)
    dashboard.read_until(lambda text: "whip=0 sent=0 all-time 7/21" in text)
    assert dashboard.quit() == 0
