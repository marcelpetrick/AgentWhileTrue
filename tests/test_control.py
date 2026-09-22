# SPDX-FileCopyrightText: 2026 Marcel Petrick
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for the control channel and the input handover it exists for.

A background service holding the lock used to keep input control until it was
stopped. These tests cover the handover that replaces that dead end, including
the two properties it must never lose: exactly one instance holds the lock at
any moment, and an action already in flight is never split from its
verification.
"""

from __future__ import annotations

import contextlib
import socket
import threading
import time
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from agent_while_true import cli, control
from agent_while_true.config import Config, Mode, Policy
from agent_while_true.control import ControlError, ControlServer
from agent_while_true.fsm import SupervisedSession
from agent_while_true.lock import SingleInstanceLock
from agent_while_true.proc import ProcessIdentity
from agent_while_true.terminal.base import SessionRef
from tests import harness as harness_module

FULL_AUTO = Policy(allow_codex_auto_resume=True)


def _ask(server: ControlServer, path: Path, op: str, handler) -> dict[str, object]:
    """Send one request while the server is polled, as the run loop polls it."""
    outcome: dict[str, object] = {}

    def client() -> None:
        try:
            outcome.update(control.request(path, op, timeout=5.0))
        except ControlError as exc:  # pragma: no cover - failure path
            outcome["error"] = str(exc)

    caller = threading.Thread(target=client)
    caller.start()
    deadline = time.monotonic() + 5.0
    while caller.is_alive() and time.monotonic() < deadline:
        server.poll(handler)
        time.sleep(0.01)
    caller.join(timeout=5.0)
    return outcome


def _serve_until(control_side: cli._InputControl, config: Config, done) -> Config:
    """Run the holder's loop step until ``done`` or a deadline, as ``_loop`` does."""
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        config, _ = control_side.tick(config)
        if done(config):
            return config
        time.sleep(0.01)
    return config


@pytest.fixture
def runtime(tmp_path: Path) -> Path:
    directory = tmp_path / "runtime"
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    return directory


def test_status_answers_with_the_mode_and_nothing_from_the_terminal(runtime: Path) -> None:
    server = ControlServer.in_directory(runtime)
    server.start()
    try:
        reply = _ask(
            server,
            runtime / control.SOCKET_FILENAME,
            control.OP_STATUS,
            lambda op: {"ok": True, "mode": "auto", "op": op},
        )
    finally:
        server.close()
    assert reply == {"ok": True, "mode": "auto", "op": control.OP_STATUS}


def test_the_socket_is_private_to_its_owner(runtime: Path) -> None:
    server = ControlServer.in_directory(runtime)
    server.start()
    try:
        assert (runtime / control.SOCKET_FILENAME).stat().st_mode & 0o077 == 0
    finally:
        server.close()
    assert not (runtime / control.SOCKET_FILENAME).exists()


def test_a_malformed_request_is_rejected_without_reaching_the_handler(runtime: Path) -> None:
    server = ControlServer.in_directory(runtime)
    server.start()
    seen: list[str] = []
    path = runtime / control.SOCKET_FILENAME

    def client() -> None:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
            sock.settimeout(5.0)
            sock.connect(str(path))
            sock.sendall(b"not json\n")
            sock.recv(1024)

    caller = threading.Thread(target=client)
    caller.start()
    deadline = time.monotonic() + 5.0
    while caller.is_alive() and time.monotonic() < deadline:
        server.poll(lambda op: seen.append(op) or {"ok": True})  # type: ignore[func-returns-value]
        time.sleep(0.01)
    caller.join(timeout=5.0)
    server.close()
    assert seen == []


def test_a_dead_instances_socket_is_replaced_but_a_live_one_is_not(runtime: Path) -> None:
    stale = runtime / control.SOCKET_FILENAME
    stale.touch()
    first = ControlServer.in_directory(runtime)
    first.start()
    try:
        second = ControlServer.in_directory(runtime)
        with pytest.raises(ControlError):
            second.start()
    finally:
        first.close()


def test_a_request_without_a_controller_reports_no_controller(runtime: Path) -> None:
    granted, detail = control.request_yield_input(runtime, timeout=1.0)
    assert not granted
    assert "no input controller" in detail


def _holder(
    tmp_path: Path, runtime: Path
) -> tuple[harness_module.Harness, cli._InputControl, Config, SingleInstanceLock]:
    """A running full-auto instance that already holds the lock."""
    config = Config(
        mode=Mode.AUTO,
        policy=FULL_AUTO,
        state_dir=tmp_path / "holder",
        runtime_dir=runtime,
    )
    kit = harness_module.build(tmp_path / "holder", config=config)
    lock = SingleInstanceLock.in_directory(runtime)
    lock.acquire()
    side = cli._InputControl(kit.supervisor, lock, config)
    config, _ = side.tick(config)
    assert side.server.active
    return kit, side, config, lock


def test_the_full_auto_key_takes_input_control_from_a_running_instance(tmp_path: Path) -> None:
    runtime = tmp_path / "runtime"
    runtime.mkdir(parents=True, mode=0o700)
    holder, holder_side, holder_config, holder_lock = _holder(tmp_path, runtime)

    watcher_config = Config(
        mode=Mode.OBSERVE,
        state_dir=tmp_path / "watcher",
        runtime_dir=runtime,
    )
    watcher = harness_module.build(tmp_path / "watcher", config=watcher_config)
    watcher_lock = SingleInstanceLock.in_directory(runtime)
    taken: dict[str, object] = {}

    def press_full_auto() -> None:
        config, message = cli._toggle_runtime_mode(watcher.supervisor, watcher_config, watcher_lock)
        taken["config"] = config
        taken["message"] = message

    presser = threading.Thread(target=press_full_auto)
    presser.start()
    holder_config = _serve_until(
        holder_side, holder_config, lambda current: current.mode is Mode.OBSERVE
    )
    presser.join(timeout=5.0)

    # The watcher at the keyboard is now the single input controller.
    assert taken["config"].mode is Mode.AUTO  # type: ignore[union-attr]
    assert taken["config"].policy.allow_codex_auto_resume  # type: ignore[union-attr]
    assert "full auto enabled" in str(taken["message"])
    assert watcher_lock.held
    # The instance that yielded cannot type any more, and knows what to restore.
    assert holder_config.mode is Mode.OBSERVE
    assert not holder_lock.held
    assert holder_side.rearm is not None
    assert not holder_side.server.active

    # While the watcher is in charge, the instance that yielded keeps its hands
    # off the lock even though it is free for a moment.
    holder.clock.advance(cli.HANDOVER_GRACE_SECONDS + 1.0)
    holder_config, _ = holder_side.tick(holder_config)
    assert holder_config.mode is Mode.OBSERVE
    assert watcher_lock.held

    # When the watcher leaves, the service takes its full-auto role back.
    watcher_lock.release()
    holder_config = _serve_until(
        holder_side, holder_config, lambda current: current.mode is Mode.AUTO
    )
    assert holder_config.mode is Mode.AUTO
    assert holder_config.policy.allow_codex_auto_resume
    assert holder_lock.held
    assert holder_side.rearm is None
    holder_side.close()
    holder_lock.release()

    # One process has one event logger, and the watcher's harness redirected it,
    # so read both files rather than guessing which one won.
    log = "".join(path.read_text() for path in tmp_path.glob("*/agent-while-true.log"))
    assert "event=input_yielded" in log
    assert "event=input_rearmed" in log


def test_a_deferred_start_arms_itself_once_the_lock_is_free(tmp_path: Path) -> None:
    """A watcher that could not take the lock at startup arms when it frees.

    This is what keeps a user service startable while an interactive watcher is
    open, instead of exiting and being restarted until systemd gives up.
    """
    runtime = tmp_path / "runtime"
    runtime.mkdir(parents=True, mode=0o700)
    wanted = Config(
        mode=Mode.AUTO,
        policy=FULL_AUTO,
        state_dir=tmp_path / "deferred",
        runtime_dir=runtime,
    )
    kit = harness_module.build(tmp_path / "deferred", config=wanted)
    incumbent = SingleInstanceLock.in_directory(runtime)
    incumbent.acquire()

    lock = SingleInstanceLock.in_directory(runtime)
    observing = replace(wanted, mode=Mode.OBSERVE)
    side = cli._InputControl(kit.supervisor, lock, observing, deferred=wanted)

    config, _ = side.tick(observing)
    assert config.mode is Mode.OBSERVE
    assert not lock.held
    assert not side.server.active

    incumbent.release()
    config = _serve_until(side, config, lambda current: current.mode is Mode.AUTO)

    assert config.mode is Mode.AUTO
    assert config.policy.allow_codex_auto_resume
    assert lock.held
    assert side.server.active
    side.close()
    lock.release()


def test_a_handover_is_refused_while_an_action_waits_for_verification(tmp_path: Path) -> None:
    runtime = tmp_path / "runtime"
    runtime.mkdir(parents=True, mode=0o700)
    _, holder_side, holder_config, holder_lock = _holder(tmp_path, runtime)
    holder_side.supervisor.sessions["pending"] = _session_awaiting_verification()

    reply = _ask(
        holder_side.server,
        runtime / control.SOCKET_FILENAME,
        control.OP_YIELD_INPUT,
        holder_side._handle,
    )

    assert reply == {"ok": False, "reason": "action-in-flight"}
    assert holder_lock.held
    assert holder_config.mode is Mode.AUTO
    holder_side.close()
    holder_lock.release()


def _session_awaiting_verification() -> SupervisedSession:
    """A session whose keystroke has been sent but not yet verified."""
    return SupervisedSession(
        ref=SessionRef(adapter="konsole", service="org.kde.konsole-1", session_id="/Sessions/1"),
        identity=ProcessIdentity(pid=1, start_time=1, tty="pts/0", exe="/usr/bin/codex"),
        provider_name="codex",
        verify_after=datetime(2026, 9, 19, 21, 0, tzinfo=UTC),
    )


# -- protocol edges: a misbehaving peer never breaks the run loop -----------


def _raw_client(path: Path, payload: bytes) -> threading.Thread:
    def send() -> None:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
            sock.connect(str(path))
            sock.sendall(payload)
            sock.shutdown(socket.SHUT_WR)
            sock.settimeout(2.0)
            with contextlib.suppress(OSError):  # the server may just close
                sock.recv(1024)

    thread = threading.Thread(target=send)
    thread.start()
    return thread


def _poll_until_done(server: ControlServer, thread: threading.Thread, handler) -> int:
    served = 0
    deadline = time.monotonic() + 5.0
    while thread.is_alive() and time.monotonic() < deadline:
        served += server.poll(handler)
        time.sleep(0.01)
    thread.join(timeout=5.0)
    return served


@pytest.mark.parametrize(
    "payload",
    [b"", b'{"op": "status"}', b"x" * 5000, b"not json\n", b'{"no": "op"}\n'],
)
def test_a_malformed_request_is_answered_without_serving(tmp_path: Path, payload: bytes) -> None:
    server = ControlServer.in_directory(tmp_path)
    server.start()
    server.start()  # idempotent while bound
    calls: list[str] = []
    try:

        def handler(op: str) -> dict[str, object]:
            calls.append(op)
            return {"ok": True}

        served = _poll_until_done(server, _raw_client(server.path, payload), handler)
    finally:
        server.close()
    if payload == b'{"op": "status"}':
        # A request without a newline is still one request once the peer is done.
        assert calls == ["status"]
        assert served == 1
    else:
        assert calls == []
        assert served == 0
    assert not server.path.exists()
    server.close()  # closing twice is harmless


def test_poll_survives_a_socket_error(tmp_path: Path) -> None:
    server = ControlServer.in_directory(tmp_path)
    assert server.poll(lambda op: {"ok": True}) == 0

    class Broken:
        def accept(self):
            raise OSError("gone")

        def close(self) -> None:
            pass

    server._sock = Broken()  # type: ignore[assignment]
    assert server.poll(lambda op: {"ok": True}) == 0
    server.close()


def test_a_successor_socket_is_not_unlinked(tmp_path: Path) -> None:
    server = ControlServer.in_directory(tmp_path)
    server.start()
    server.path.unlink()
    server.close()  # the path is gone: nothing to remove, nothing raised
    assert not server.path.exists()


def _fake_controller(path: Path, reply: bytes) -> threading.Thread:
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    listener.bind(str(path))
    listener.listen(1)

    def answer() -> None:
        with listener:
            connection, _ = listener.accept()
            with connection:
                connection.recv(1024)
                connection.sendall(reply)

    thread = threading.Thread(target=answer)
    thread.start()
    return thread


@pytest.mark.parametrize("reply", [b"garbage\n", b"[1, 2]\n"])
def test_a_malformed_reply_is_a_control_error(tmp_path: Path, reply: bytes) -> None:
    path = tmp_path / "control.sock"
    thread = _fake_controller(path, reply)
    with pytest.raises(ControlError, match="malformed reply"):
        control.request(path, "status", timeout=2.0)
    thread.join(timeout=5.0)


def test_a_refused_yield_reports_the_reason(tmp_path: Path) -> None:
    thread = _fake_controller(tmp_path / control.SOCKET_FILENAME, b'{"ok": false}\n')
    assert control.request_yield_input(tmp_path, timeout=2.0) == (False, "refused")
    thread.join(timeout=5.0)
