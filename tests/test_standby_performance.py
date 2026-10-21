# SPDX-FileCopyrightText: 2026 Marcel Petrick
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""A deferred service sleeps cheaply, then revalidates its entire ownership gap."""

import io
import signal
from dataclasses import replace
from unittest.mock import Mock

import pytest

from agent_while_true import cli, state_store
from agent_while_true.config import Config, Mode
from agent_while_true.lock import SingleInstanceLock
from agent_while_true.policy import capacity_idempotency_key
from agent_while_true.states import ActionState
from tests import harness, screens


def _forbidden(*args, **kwargs):
    pytest.fail("standby performed observation work")


def _loop_world(tmp_path, monkeypatch, *, mode=Mode.AUTO, once=False, interactive=False):
    wanted = Config(mode=mode, scan_interval=30)
    kit = harness.build(tmp_path, config=wanted)
    wanted = kit.supervisor.config
    observing = replace(wanted, mode=Mode.OBSERVE)
    kit.supervisor.config = observing
    lock = SingleInstanceLock.in_directory(wanted.resolved_runtime_dir())
    incumbent = SingleInstanceLock.in_directory(wanted.resolved_runtime_dir())
    incumbent.acquire()
    signals = {}
    monkeypatch.setattr(
        cli.signal, "signal", lambda signum, callback: signals.update({signum: callback})
    )
    monkeypatch.setattr(cli.time, "monotonic", kit.clock.mono)
    monkeypatch.setattr(cli.HealthMonitor, "start", Mock())
    monkeypatch.setattr(cli.HealthMonitor, "stop", Mock())
    monkeypatch.setattr(cli.sys.stdin, "isatty", lambda: interactive)

    class Output(io.StringIO):
        def isatty(self):
            return interactive

    args = cli.build_parser().parse_args(["run", "--all", *(["--once"] if once else [])])
    return kit, wanted, observing, lock, incumbent, signals, args, Output()


def test_deferred_service_does_no_observation_work_or_samples(tmp_path, monkeypatch):
    kit, wanted, observing, lock, incumbent, signals, args, stream = _loop_world(
        tmp_path, monkeypatch
    )
    for name in ("tick", "prune_and_rebind", "report_approval_status"):
        monkeypatch.setattr(type(kit.supervisor), name, _forbidden)
    monkeypatch.setattr(cli, "_sync_all_sessions", _forbidden)
    monkeypatch.setattr(cli, "read_activity_history", _forbidden)
    monkeypatch.setattr(cli.ObservationMetrics, "record", _forbidden)
    monkeypatch.setattr(cli.HealthMonitor, "start", _forbidden)
    sleeps = []

    def sleep(seconds):
        assert 0 < seconds <= 1
        sleeps.append(seconds)
        kit.clock.advance(seconds)
        if len(sleeps) == 12:
            signals[signal.SIGTERM](signal.SIGTERM, None)

    monkeypatch.setattr(cli.time, "sleep", sleep)
    try:
        assert cli._loop(kit.supervisor, observing, args, stream, lock, deferred=wanted) == 130
    finally:
        incumbent.release()
        lock.release()
    assert len(sleeps) == 12
    assert stream.getvalue() == ""
    assert not kit.sent
    assert not kit.supervisor.store.records
    assert not kit.supervisor.store.episodes


@pytest.mark.parametrize("state", [ActionState.PLANNED, ActionState.SENT, ActionState.FAILED])
def test_reclaim_reloads_intent_and_spent_budget_before_fresh_identity_scan(
    tmp_path, monkeypatch, state
):
    kit, wanted, observing, lock, incumbent, signals, args, stream = _loop_world(
        tmp_path, monkeypatch
    )
    old = kit.inspector.add_codex(4321, start_time=11)
    ref = kit.terminal.add(
        "/Sessions/1", shell_pid=100, foreground_pid=4321, screen=screens.CODEX_MODEL_CAPACITY
    )
    kit.supervisor.select(ref, old.identity, "codex", "old identity")
    order = []
    original_load = state_store.StateStore.load
    original_prune = kit.supervisor.prune_and_rebind
    original_sync = cli._sync_all_sessions
    original_tick = kit.supervisor.tick

    def load(store, *args, **kwargs):
        if store is kit.supervisor.store:
            order.append("load")
        return original_load(store, *args, **kwargs)

    def prune(self):
        order.append("prune")
        original_prune()

    def sync(*args, **kwargs):
        order.append("discover")
        original_sync(*args, **kwargs)

    def tick(self):
        order.append("scan")
        assert kit.supervisor.store.records[key].attempts == 3
        assert kit.supervisor.sessions[ref.key()].identity.start_time == 22
        return original_tick()

    monkeypatch.setattr(state_store.StateStore, "load", load)
    monkeypatch.setattr(type(kit.supervisor), "prune_and_rebind", prune)
    monkeypatch.setattr(cli, "_sync_all_sessions", sync)
    monkeypatch.setattr(type(kit.supervisor), "tick", tick)
    monkeypatch.setattr(cli, "read_activity_history", _forbidden)
    monkeypatch.setattr(state_store, "_now_text", lambda: kit.clock.now().isoformat())
    key = ""
    sleeps = 0

    def sleep(seconds):
        nonlocal sleeps, key
        sleeps += 1
        kit.clock.advance(seconds)
        harness.refresh_quota(kit)
        if sleeps == 2:
            new = kit.inspector.add_codex(4321, start_time=22)
            key = capacity_idempotency_key(ref, new.identity)
            writer = state_store.StateStore.in_directory(tmp_path).load(now=kit.clock.now())
            writer.plan(key, provider="codex", session=ref.key(), process=new.identity.key())
            writer.mark(key, state)
            writer.records[key].attempts = 3
            writer.save()
            incumbent.release()
        elif "scan" in order:
            signals[signal.SIGTERM](signal.SIGTERM, None)

    monkeypatch.setattr(cli.time, "sleep", sleep)
    try:
        assert cli._loop(kit.supervisor, observing, args, stream, lock, deferred=wanted) == 130
    finally:
        incumbent.release()
        lock.release()
    assert order[:4] == ["load", "prune", "discover", "scan"]
    assert not kit.sent
    assert kit.supervisor.store.records[key].attempts == 3
    assert kit.supervisor.activity.unblock_actions == 0
    assert "auto-yes on permission prompts: OFF" not in stream.getvalue()  # headless, no frame


@pytest.mark.parametrize(
    ("once", "interactive", "explicit_observe"),
    [(True, False, False), (False, True, False), (False, False, True)],
)
def test_explicit_observers_interactive_dashboards_and_once_still_scan(
    tmp_path, monkeypatch, once, interactive, explicit_observe
):
    kit, wanted, observing, lock, incumbent, signals, args, stream = _loop_world(
        tmp_path, monkeypatch, once=once, interactive=interactive
    )
    calls = []
    monkeypatch.setattr(type(kit.supervisor), "tick", lambda self: calls.append("scan") or [])
    monkeypatch.setattr(cli.TerminalKeys, "read", lambda self, timeout: "q")
    monkeypatch.setattr(
        cli, "read_activity_history", lambda *args, **kwargs: calls.append("history") or []
    )

    def sleep(seconds):
        signals[signal.SIGTERM](signal.SIGTERM, None)

    monkeypatch.setattr(cli.time, "sleep", sleep)
    try:
        result = cli._loop(
            kit.supervisor,
            observing,
            args,
            stream,
            lock,
            deferred=None if explicit_observe else wanted,
        )
    finally:
        incumbent.release()
        lock.release()
    assert result == (0 if once or interactive else 130)
    assert calls == (["scan", "history"] if interactive else ["scan"])
    assert not kit.sent


def test_service_defers_before_discovery_but_reclaims_without_a_control_socket(
    tmp_path, monkeypatch
):
    kit, wanted, observing, lock, incumbent, _signals, args, stream = _loop_world(
        tmp_path, monkeypatch
    )
    del observing, lock
    monkeypatch.setattr(cli, "_check_privileges", lambda *args: True)
    monkeypatch.setattr(cli, "_build_supervisor", lambda *args: kit.supervisor)
    monkeypatch.setattr(cli, "discover", _forbidden)

    def loop(supervisor, config, args, stream, lock, *, deferred):
        assert deferred is wanted
        assert config.mode is Mode.OBSERVE
        assert supervisor.sessions == {}
        side = cli._InputControl(supervisor, lock, config, deferred=deferred)
        current, _ = side.tick(config)
        assert current.mode is Mode.OBSERVE
        incumbent.release()
        current, _ = side.tick(current)
        assert current.mode is Mode.AUTO
        assert lock.held
        side.close()
        return 0

    monkeypatch.setattr(cli, "_loop", loop)
    try:
        assert cli.command_run(wanted, args, stream, lambda prompt: "") == 0
    finally:
        incumbent.release()
    assert "standing by" in stream.getvalue()
    assert not kit.sent


def test_service_yields_into_standby_and_discards_the_measurement_gap(tmp_path, monkeypatch):
    kit, wanted, _observing, lock, incumbent, signals, args, stream = _loop_world(
        tmp_path, monkeypatch
    )
    incumbent.release()
    lock.acquire()
    kit.supervisor.config = wanted
    monkeypatch.setattr(cli.HealthMonitor, "start", _forbidden)
    monkeypatch.setattr(cli, "read_activity_history", _forbidden)
    trace = []
    original_control_tick = cli._InputControl.tick
    control_calls = 0
    scans = 0
    sleeps = 0

    def control_tick(side, config):
        nonlocal control_calls
        control_calls += 1
        if control_calls == 2:
            assert side._yield_input()["ok"]
            incumbent.acquire()
            return side.config, side.note
        return original_control_tick(side, config)

    def tick(self):
        nonlocal scans
        scans += 1
        trace.append("scan")
        return []

    def sleep(seconds):
        nonlocal sleeps
        sleeps += 1
        kit.clock.advance(seconds)
        if sleeps == 5:
            assert scans == 1
            incumbent.release()
        if scans == 2:
            signals[signal.SIGTERM](signal.SIGTERM, None)

    monkeypatch.setattr(cli._InputControl, "tick", control_tick)
    monkeypatch.setattr(type(kit.supervisor), "tick", tick)
    monkeypatch.setattr(cli.ObservationMetrics, "reset", lambda self: trace.append("gap"))
    monkeypatch.setattr(
        cli.ObservationMetrics, "record", lambda self, *args, **kwargs: trace.append("sample")
    )
    monkeypatch.setattr(cli.time, "sleep", sleep)
    try:
        assert cli._loop(kit.supervisor, wanted, args, stream, lock) == 130
    finally:
        incumbent.release()
        lock.release()
    assert scans == 2
    assert trace == ["scan", "sample", "gap", "gap", "scan", "sample", "gap"]


def test_non_all_headless_start_preserves_explicit_session_selection(tmp_path, monkeypatch):
    kit, wanted, _observing, _lock, incumbent, _signals, args, stream = _loop_world(
        tmp_path, monkeypatch
    )
    args.all = False
    info = kit.inspector.add_claude(123)
    kit.terminal.add("/Sessions/1", shell_pid=100, foreground_pid=123)
    assert info
    monkeypatch.setattr(cli, "_check_privileges", lambda *args: True)
    monkeypatch.setattr(cli, "_build_supervisor", lambda *args: kit.supervisor)
    monkeypatch.setattr(cli, "SystemInspector", lambda: kit.inspector)
    selected = []

    def select(config, candidates, **kwargs):
        selected.extend(candidates)

    monkeypatch.setattr(cli, "_select_sessions", select)
    try:
        assert cli.command_run(wanted, args, stream, lambda prompt: "q") == 0
    finally:
        incumbent.release()
    assert len(selected) == 1
    assert "Nothing selected" in stream.getvalue()


def test_headless_all_start_with_free_lock_discovers_and_arms_normally(tmp_path, monkeypatch):
    kit, wanted, _observing, _lock, incumbent, _signals, args, stream = _loop_world(
        tmp_path, monkeypatch
    )
    incumbent.release()
    info = kit.inspector.add_claude(123)
    ref = kit.terminal.add("/Sessions/1", shell_pid=100, foreground_pid=123)
    monkeypatch.setattr(cli, "_check_privileges", lambda *args: True)
    monkeypatch.setattr(cli, "_build_supervisor", lambda *args: kit.supervisor)
    monkeypatch.setattr(cli, "SystemInspector", lambda: kit.inspector)

    def loop(supervisor, config, args, stream, lock, *, deferred):
        assert deferred is None
        assert config.mode is Mode.AUTO
        assert supervisor.sessions[ref.key()].identity == info.identity
        assert lock.held
        return 0

    monkeypatch.setattr(cli, "_loop", loop)
    assert cli.command_run(wanted, args, stream, lambda prompt: "") == 0
    assert not kit.sent
