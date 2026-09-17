# SPDX-FileCopyrightText: 2026 Marcel Petrick
# SPDX-License-Identifier: GPL-3.0-or-later
"""Presentation key bursts must not multiply terminal/provider polling."""

import io
from dataclasses import replace

import pytest

from agent_while_true import cli
from agent_while_true.config import Mode
from agent_while_true.lock import SingleInstanceLock
from tests.harness import build


@pytest.mark.parametrize(
    ("pressed", "elapsed", "expected"),
    [
        (list("j" * 20 + "q"), 0.01, 1),
        (list("jrjq"), 0.01, 2),
        (list("jppjq"), 0.01, 2),
        (list("jprpjq"), 0.01, 2),
        (list("j-jq"), 0.01, 2),
        (list("jAjq"), 0.01, 2),
        (["", "", "q"], 2.1, 3),
    ],
)
def test_keys_do_not_accelerate_scans(tmp_path, monkeypatch, pressed, elapsed, expected):
    kit = build(tmp_path, mode=Mode.OBSERVE)
    clock = [100.0]
    ticks = []
    keys = iter(pressed)

    def read(self, timeout):
        assert timeout > 0
        clock[0] += elapsed
        return next(keys)

    class Output(io.StringIO):
        def isatty(self):
            return True

    monkeypatch.setattr(cli.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(cli.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(cli.TerminalKeys, "read", read)
    monkeypatch.setattr(cli.HealthMonitor, "start", lambda self: None)
    monkeypatch.setattr(cli.Supervisor, "tick", lambda self: ticks.append(clock[0]) or [])
    args = cli.build_parser().parse_args(["run", "--observe"])
    lock = SingleInstanceLock.in_directory(tmp_path / "runtime")
    assert cli._loop(kit.supervisor, kit.supervisor.config, args, Output(), lock) == 0
    assert len(ticks) == expected
    assert kit.sent == []


def test_service_status_is_fetched_on_its_own_interval(tmp_path, monkeypatch):
    """The dashboard redraw rate must not become the status-API request rate."""
    intervals = []

    class Recorder:
        def __init__(self, *, interval):
            intervals.append(interval)

        def start(self):
            pass

        def stop(self):
            pass

        def snapshot(self):
            return {}

    kit = build(tmp_path, mode=Mode.OBSERVE)
    config = replace(kit.supervisor.config, status_poll_interval=1.0, service_status_interval=300.0)
    monkeypatch.setattr(cli, "HealthMonitor", Recorder)
    args = cli.build_parser().parse_args(["run", "--observe", "--once"])
    lock = SingleInstanceLock.in_directory(tmp_path / "runtime")

    assert cli._loop(kit.supervisor, config, args, io.StringIO(), lock) == 0
    assert intervals == [300.0]


def test_the_default_status_interval_is_far_coarser_than_the_redraw(tmp_path):
    config = build(tmp_path, mode=Mode.OBSERVE).supervisor.config
    assert config.service_status_interval >= 60 * config.status_poll_interval
