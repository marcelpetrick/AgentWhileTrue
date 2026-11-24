# SPDX-FileCopyrightText: 2026 Marcel Petrick
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""An interactive dashboard attaches to the background service: one watcher, not two."""

import io
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import Mock

import pytest

from agent_while_true import cli
from agent_while_true.config import Config, Mode
from agent_while_true.control import (
    VIEW_SOCKET_FILENAME,
    ControlError,
    ControlServer,
    request,
    request_view,
    view_available,
)
from agent_while_true.fsm import Supervisor
from agent_while_true.lock import SingleInstanceLock
from tests import harness
from tests.conftest import REAL_VIEW_WAIT
from tests.pty_dashboard import ROOT, Dashboard


class Interactive(io.StringIO):
    def isatty(self) -> bool:
        return True


class Headless(io.StringIO):
    def isatty(self) -> bool:
        return False


def _service(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, client) -> tuple[int, object]:
    """Run the headless full-auto loop until ``client`` has finished talking to it."""
    kit = harness.build(tmp_path, config=Config(mode=Mode.AUTO, scan_interval=30))
    config = kit.supervisor.config
    lock = SingleInstanceLock.in_directory(config.resolved_runtime_dir())
    lock.acquire()
    signals: dict[int, object] = {}
    monkeypatch.setattr(cli.signal, "signal", lambda signum, cb: signals.update({signum: cb}))
    monkeypatch.setattr(cli.HealthMonitor, "start", Mock())
    monkeypatch.setattr(cli.HealthMonitor, "stop", Mock())
    monkeypatch.setattr(cli.sys.stdin, "isatty", lambda: False)
    worker: list[threading.Thread] = []

    def wait(self: ControlServer, timeout: float) -> bool:
        if not worker:
            worker.append(threading.Thread(target=client, args=(config.resolved_runtime_dir(),)))
            worker[0].start()
        ready = REAL_VIEW_WAIT(self, 0.2)
        if not worker[0].is_alive():
            signals[signal.SIGTERM](signal.SIGTERM, None)  # type: ignore[operator]
        return ready

    monkeypatch.setattr(ControlServer, "wait", wait)
    args = cli.build_parser().parse_args(["run", "--auto", "--all"])
    try:
        code = cli._loop(kit.supervisor, config, args, Headless(), lock)
    finally:
        lock.release()
    assert not view_available(config.resolved_runtime_dir())
    return code, kit


def test_the_service_applies_attached_keys_and_returns_its_frame(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    replies: list[dict[str, object]] = []

    def client(runtime: Path) -> None:
        replies.append(request_view(runtime, {"keys": ["y", "q"], "width": 168, "height": 60}))
        replies.append(request_view(runtime, {"keys": [], "width": "wide", "height": 5}))
        replies.append(request(runtime / VIEW_SOCKET_FILENAME, "status"))
        replies.append(request(runtime / VIEW_SOCKET_FILENAME, "view", payload={"keys": "y"}))

    code, kit = _service(tmp_path, monkeypatch, client)

    # q closes a viewer, never the service: only the test's SIGTERM ended it.
    assert code == cli.EXIT_INTERRUPTED
    first, second, status, malformed = replies
    assert first["pid"] == os.getpid()
    assert first["mode"] == "auto"
    # Full auto started with auto-yes on; the viewer's y switched it off there.
    assert "auto-yes on permission prompts: OFF" in str(first["frame"])
    assert len(str(second["frame"]).splitlines()) <= 5
    assert status == {"ok": False, "reason": "unknown-op"}
    assert malformed == {"ok": False, "reason": "malformed-request"}
    log = (tmp_path / "agent-while-true.log").read_text()
    assert "event=auto_yes_toggled enabled=true source=start" in log
    assert "event=auto_yes_toggled enabled=false" in log
    assert kit.sent == []


def test_an_attached_whip_cracks_on_the_service_without_animating_there(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    animations = Mock()
    monkeypatch.setattr(cli, "_animate_whip", animations)
    replies: list[dict[str, object]] = []

    def client(runtime: Path) -> None:
        replies.append(request_view(runtime, {"keys": ["w"], "width": 100, "height": 30}))

    _service(tmp_path, monkeypatch, client)

    animations.assert_not_called()
    assert "whip cracked" in (tmp_path / "agent-while-true.log").read_text().replace("_", " ")


def test_health_polling_stops_once_no_dashboard_is_attached(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = [1000.0]
    real_monotonic = time.monotonic
    monkeypatch.setattr(cli, "VIEW_IDLE_SECONDS", 0.0)
    replies: list[dict[str, object]] = []

    def client(runtime: Path) -> None:
        replies.append(request_view(runtime, {"keys": [], "width": 168, "height": 40}))
        clock[0] += 1

    monkeypatch.setattr(cli.time, "monotonic", lambda: real_monotonic() + clock[0])
    _service(tmp_path, monkeypatch, client)

    assert replies
    cli.HealthMonitor.start.assert_called()  # type: ignore[attr-defined]
    # Once when the viewer went idle, once more when the loop ended.
    assert cli.HealthMonitor.stop.call_count >= 2  # type: ignore[attr-defined]


def test_an_attached_view_uses_the_saved_display_preferences(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "preferences.json").write_text(
        '{"details_visible":true,"help_visible":false,"history_length":20,'
        '"show_events":true,"theme":"vivid","version":1}'
    )
    replies: list[dict[str, object]] = []

    def client(runtime: Path) -> None:
        replies.append(request_view(runtime, {"keys": [], "width": 168, "height": 40}))

    _service(tmp_path, monkeypatch, client)

    assert replies[0]["theme"] == "vivid"


def _fake_service(runtime: Path, frames: int) -> tuple[threading.Thread, list[list[str]]]:
    """A view socket that answers ``frames`` requests, then disappears."""
    server = ControlServer.in_directory(runtime, VIEW_SOCKET_FILENAME)
    server.start()
    received: list[list[str]] = []

    def handler(op: str, payload: dict[str, object]) -> dict[str, object]:
        received.append(list(payload["keys"]))  # type: ignore[call-overload]
        return {"ok": True, "frame": "FRAME", "pid": 4242, "version": "9.9", "refresh": 0.01}

    def serve() -> None:
        while len(received) < frames:
            if REAL_VIEW_WAIT(server, 0.05):
                server.poll(handler)
        server.close()

    thread = threading.Thread(target=serve)
    thread.start()
    return thread, received


def _keys(monkeypatch: pytest.MonkeyPatch, sequence: list[str]) -> None:
    pressed = iter(sequence)
    monkeypatch.setattr(cli.TerminalKeys, "read", lambda self, timeout: next(pressed, "q"))


def test_the_dashboard_forwards_keys_and_quits_only_itself(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime = tmp_path / "run"
    thread, received = _fake_service(runtime, frames=3)
    animations = Mock()
    monkeypatch.setattr(cli, "_animate_whip", animations)
    _keys(monkeypatch, ["y", "w", "q"])
    stream = Interactive()
    args = cli.build_parser().parse_args(["run"])

    assert cli._attach(Config(runtime_dir=runtime), args, stream) == cli.EXIT_OK
    thread.join(5)

    assert received == [[], ["y"], ["w"]]
    animations.assert_called_once()
    output = stream.getvalue()
    assert "attached to the background watcher (PID 4242, v9.9)" in output
    assert "q closes this view only" in output
    assert "FRAME" in output
    assert output.endswith(cli.SHOW_CURSOR)


def test_a_vanished_service_closes_the_view_with_an_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime = tmp_path / "run"
    thread, received = _fake_service(runtime, frames=1)
    monkeypatch.setattr(cli, "VIEW_GIVE_UP_SECONDS", 0.3)
    monkeypatch.setattr(cli.TerminalKeys, "read", lambda self, timeout: time.sleep(0.05) or "")
    stream = Interactive()

    code = cli._attach(Config(runtime_dir=runtime), cli.build_parser().parse_args(["run"]), stream)
    thread.join(5)

    assert code == cli.EXIT_ERROR
    assert received == [[]]
    # It retried for the grace period before giving up.
    assert "waiting for the background watcher" in stream.getvalue()
    assert "stopped answering" in stream.getvalue()


def _flaky_view(monkeypatch: pytest.MonkeyPatch, failures: set[int]) -> list[list[str]]:
    """Replace the view request; the listed request numbers time out."""
    sent: list[list[str]] = []

    def fake(runtime: Path, payload: dict[str, object]) -> dict[str, object]:
        sent.append(list(payload["keys"]))  # type: ignore[call-overload]
        if len(sent) in failures:
            raise ControlError("timed out")
        return {"ok": True, "frame": f"FRAME{len(sent)}", "pid": 7, "version": "9.9"}

    monkeypatch.setattr(cli, "view_available", lambda runtime_dir: True)
    monkeypatch.setattr(cli, "request_view", fake)
    return sent


def test_a_slow_reply_keeps_the_view_and_never_resends_keys(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One reply slower than the timeout is a busy service, not a gone one."""
    sent = _flaky_view(monkeypatch, failures={2})
    # y goes out with request 2, which times out; the outage notice reads one
    # key ("" here), then the view recovers and quits on q.
    _keys(monkeypatch, ["y", "", "", "q"])
    stream = Interactive()

    code = cli._attach(Config(runtime_dir=tmp_path), cli.build_parser().parse_args(["run"]), stream)

    assert code == cli.EXIT_OK
    # The service may have applied the y of the timed-out request: it is
    # never sent again, so a toggle cannot flip back.
    assert sent == [[], ["y"], [], []]
    output = stream.getvalue()
    assert "waiting for the background watcher" in output
    assert "FRAME4" in output
    assert "stopped answering" not in output


def test_q_closes_a_view_that_waits_for_a_silent_service(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _flaky_view(monkeypatch, failures={2, 3, 4})
    _keys(monkeypatch, ["", "", "q"])
    stream = Interactive()

    code = cli._attach(Config(runtime_dir=tmp_path), cli.build_parser().parse_args(["run"]), stream)

    assert code == cli.EXIT_OK
    assert "stopped answering" not in stream.getvalue()


def test_a_long_scan_serves_frames_and_holds_keys_until_it_ends(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A scan longer than the viewer's timeout still answers it between sessions.

    Keys that arrive mid-scan wait for the scan to end, so no switch changes
    between a session's revalidation and its send.
    """
    during: list[dict[str, object]] = []
    auto_yes_during: list[str] = []
    original_tick = Supervisor.tick

    def slow_tick(self: Supervisor) -> list:
        if not during:
            runtime = self.config.resolved_runtime_dir()
            client = threading.Thread(
                target=lambda: during.append(
                    request_view(runtime, {"keys": ["y"], "width": 168, "height": 60})
                )
            )
            client.start()
            deadline = time.monotonic() + 5
            while client.is_alive() and time.monotonic() < deadline:
                self.between_steps()  # a per-session step of a long scan
                time.sleep(0.01)
            client.join(1)
            log = (tmp_path / "agent-while-true.log").read_text()
            auto_yes_during.append("enabled=false" if "enabled=false" in log else "unchanged")
        return original_tick(self)

    monkeypatch.setattr(Supervisor, "tick", slow_tick)

    def client(runtime: Path) -> None:
        # By the first idle wait the held y has been applied after the scan.
        during.append(request_view(runtime, {"keys": [], "width": 168, "height": 60}))

    _service(tmp_path, monkeypatch, client)

    first, after = during[0], during[-1]
    assert "auto-yes on permission prompts: ON" in str(first["frame"])
    assert auto_yes_during == ["unchanged"]
    assert "auto-yes on permission prompts: OFF" in str(after["frame"])


def test_a_socket_that_never_answers_leaves_starting_a_watcher(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(cli, "view_available", lambda runtime_dir: True)
    args = cli.build_parser().parse_args(["run"])

    assert cli._attach(Config(runtime_dir=tmp_path), args, Interactive()) is None


def test_without_a_service_there_is_nothing_to_attach_to(tmp_path: Path) -> None:
    args = cli.build_parser().parse_args(["run"])
    assert cli._attach(Config(runtime_dir=tmp_path), args, Interactive()) is None


def test_a_reply_without_a_frame_is_an_error(tmp_path: Path) -> None:
    server = ControlServer.in_directory(tmp_path, VIEW_SOCKET_FILENAME)
    server.start()
    answered = threading.Thread(
        target=lambda: (
            REAL_VIEW_WAIT(server, 2),
            server.poll(lambda op, payload: {"ok": True}),
        )
    )
    answered.start()
    try:
        with pytest.raises(ControlError):
            request_view(tmp_path, {"keys": []})
    finally:
        answered.join(5)
        server.close()


def test_the_real_wait_wakes_when_a_client_connects(tmp_path: Path) -> None:
    server = ControlServer.in_directory(tmp_path, VIEW_SOCKET_FILENAME)
    assert REAL_VIEW_WAIT(server, 0) is False  # not started: a plain sleep
    server.start()
    try:
        started = time.monotonic()
        assert REAL_VIEW_WAIT(server, 0.01) is False
        assert view_available(tmp_path)
        assert REAL_VIEW_WAIT(server, 5) is True
        assert time.monotonic() - started < 5
    finally:
        server.close()


def test_run_attaches_instead_of_starting_a_watcher(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(cli.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(cli, "_check_privileges", lambda config, stream: True)
    monkeypatch.setattr(cli, "_attach", lambda config, args, stream: cli.EXIT_OK)
    monkeypatch.setattr(cli, "_build_supervisor", Mock(side_effect=AssertionError("watcher")))
    args = cli.build_parser().parse_args(["run", "--auto"])

    assert cli.command_run(Config(), args, Interactive(), input) == cli.EXIT_OK

    standalone = cli.build_parser().parse_args(["run", "--standalone"])
    with pytest.raises(AssertionError, match="watcher"):
        cli.command_run(Config(), standalone, Interactive(), input)


def _environment(home: Path) -> dict[str, str]:
    return {
        "PATH": str(Path(sys.executable).parent),
        "PYTHONPATH": str(ROOT / "src"),
        "HOME": str(home),
        "XDG_STATE_HOME": str(home / "state"),
        "XDG_CONFIG_HOME": str(home / "config"),
        "http_proxy": "http://127.0.0.1:9",
        "https_proxy": "http://127.0.0.1:9",
    }


def test_a_real_dashboard_attaches_to_a_real_service(tmp_path: Path) -> None:
    """Two processes on the pseudo-terminal level: the service and a viewer."""
    # AF_UNIX paths are limited to 107 bytes; a test's tmp_path can exceed it.
    short = Path(tempfile.mkdtemp(prefix="awt", dir="/tmp"))
    runtime_env = {"XDG_RUNTIME_DIR": str(short)}
    service = subprocess.Popen(
        [sys.executable, "-m", "agent_while_true.cli", "run", "--auto", "--all", "--no-fzf"],
        env={**_environment(tmp_path), **runtime_env},
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        runtime = short / "agent-while-true"
        deadline = time.monotonic() + 20
        while not view_available(runtime):
            assert time.monotonic() < deadline, "the service never served its view"
            assert service.poll() is None
            time.sleep(0.05)

        dashboard = Dashboard(tmp_path, env=runtime_env)
        dashboard.read_until(
            lambda text: (
                f"attached to the background watcher (PID {service.pid}" in text
                and "auto-yes on permission prompts: ON" in text
                and "[A] auto-resume on limit: ON" in text
            ),
            timeout=20,
        )
        start = len(dashboard.text)
        dashboard.press("y")
        dashboard.read_until(lambda text: "auto-yes on permission prompts: OFF" in text[start:])
        # A frozen service (a long scan, a stalled D-Bus call) is not a gone
        # one: the view waits, then carries on once the service answers.
        service.send_signal(signal.SIGSTOP)
        start = len(dashboard.text)
        dashboard.read_until(
            lambda text: "waiting for the background watcher" in text[start:], timeout=20
        )
        service.send_signal(signal.SIGCONT)
        start = len(dashboard.text)
        dashboard.read_until(
            lambda text: f"attached to the background watcher (PID {service.pid}" in text[start:],
            timeout=20,
        )
        assert "stopped answering" not in dashboard.text
        assert dashboard.quit() == 0
        # The viewer is gone; the one watcher keeps running.
        assert service.poll() is None
        assert view_available(runtime)

        standalone = Dashboard(tmp_path, "--standalone", env=runtime_env)
        standalone.read_until(lambda text: "auto-resume on limit" in text, timeout=20)
        assert "attached to the background watcher" not in standalone.text
        assert standalone.quit() == 0
    finally:
        service.send_signal(signal.SIGCONT)
        service.send_signal(signal.SIGTERM)
        assert service.wait(20) == cli.EXIT_INTERRUPTED
        shutil.rmtree(short, ignore_errors=True)
