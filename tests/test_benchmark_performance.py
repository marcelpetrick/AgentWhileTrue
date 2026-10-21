# SPDX-FileCopyrightText: 2026 Marcel Petrick
# SPDX-License-Identifier: GPL-3.0-or-later

"""The benchmark uses invented evidence and emits metadata only."""

import json
import os
import runpy
import subprocess
import sys
from pathlib import Path

import pytest

from agent_while_true import fsm, quota
from agent_while_true.terminal import konsole
from agent_while_true.terminal.fake import FakeAdapter
from tests.harness import FakeInspector, ScriptedQuota

SCRIPT = Path(__file__).parents[1] / "scripts" / "benchmark-performance.py"


def run_benchmark(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "PYTHONPATH": str(SCRIPT.parents[1] / "src")},
        timeout=20,
    )


def test_benchmark_emits_only_synthetic_timing_and_operation_metadata() -> None:
    result = run_benchmark("--rounds", "2", "--archived", "8")
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["quota"]["files"] == 12
    assert report["quota"]["sessions"] == 4
    assert len(report["quota"]["warm_json_parses_per_scan"]) == 2
    assert report["quota"]["warm_median_ms"] >= 0
    assert "@" not in result.stdout
    assert "source" not in report


@pytest.mark.parametrize("value", ["0", "-1", "10001", "not-a-number"])
def test_benchmark_rejects_invalid_workload(value: str) -> None:
    assert run_benchmark("--rounds", value).returncode == 2


def test_live_benchmark_only_observes_and_never_ticks_or_sends(monkeypatch) -> None:
    terminal = FakeAdapter()
    inspector = FakeInspector()
    info = inspector.add_claude(12345)
    terminal.add("/Sessions/1", shell_pid=100, foreground_pid=info.pid)
    monkeypatch.setattr(konsole, "KonsoleAdapter", lambda: terminal)
    monkeypatch.setattr(fsm, "SystemInspector", lambda: inspector)
    monkeypatch.setattr(quota, "default_sources", lambda path: {"claude": ScriptedQuota()})

    def forbidden(*args, **kwargs):
        pytest.fail("read-only benchmark tried to advance or send")

    monkeypatch.setattr(fsm.Supervisor, "tick", forbidden)
    monkeypatch.setattr(FakeAdapter, "send_text", forbidden)
    namespace = runpy.run_path(str(SCRIPT))
    report = namespace["live_scan_benchmark"](2)
    assert report["sessions"] == 1
    assert report["rounds"] == 2
    assert not terminal.sent
