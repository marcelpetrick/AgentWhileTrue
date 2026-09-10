# SPDX-FileCopyrightText: 2026 Marcel Petrick
# SPDX-License-Identifier: GPL-3.0-or-later
"""Presentation key bursts must not multiply terminal/provider polling."""

import io

import pytest

from agent_watch import cli
from agent_watch.config import Mode
from agent_watch.lock import SingleInstanceLock
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
