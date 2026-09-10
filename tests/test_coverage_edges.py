# SPDX-FileCopyrightText: 2026 Marcel Petrick <mail@marcelpetrick.it>
# SPDX-License-Identifier: GPL-3.0-or-later
"""Failure-path coverage for process, identity, diagnostics, and status I/O."""

from __future__ import annotations

import json
import subprocess
import time
import urllib.error
from datetime import UTC, datetime
from pathlib import Path
from typing import ClassVar

import pytest

from agent_watch import classify, doctor, identity, proc
from agent_watch.classify import ProcessClass
from agent_watch.proc import ProcessIdentity, ProcessInfo
from agent_watch.service_health import (
    HealthMonitor,
    HealthState,
    ProviderHealth,
    StatusPageClient,
    parse_summary,
)


def _info(**changes: object) -> ProcessInfo:
    values = {
        "identity": ProcessIdentity(44, 55, "pts/2", "/usr/bin/tool"),
        "ppid": 1,
        "comm": "tool",
        "cmdline": ("tool",),
        "cwd": "/tmp",
        "environ_keys": frozenset(),
    }
    values.update(changes)
    return ProcessInfo(**values)  # type: ignore[arg-type]


@pytest.mark.parametrize("value", [None, 4, "", "a@b", "x" * 255 + "@example.com"])
def test_identity_rejects_non_email_claims(value: object) -> None:
    assert identity._valid_email(value) is None


@pytest.mark.parametrize("token", [None, "one.two", "a.@@@.c", "a.W10.c", "a.NA.c"])
def test_identity_rejects_malformed_jwt_payloads(token: object) -> None:
    assert identity._decode_jwt_payload(token) is None


def test_identity_refuses_wrong_owner_auth(tmp_path: Path, monkeypatch) -> None:
    auth = tmp_path / "auth.json"
    auth.write_text("{}")
    auth.chmod(0o600)
    real_stat = auth.stat()
    monkeypatch.setattr(
        Path,
        "stat",
        lambda self: type(
            "S", (), {"st_uid": real_stat.st_uid + 1, "st_mode": 0o600, "st_size": 2}
        )(),
    )
    assert identity._codex_auth(auth) is None


def test_identity_handles_missing_tokens_and_account_id(tmp_path: Path) -> None:
    auth = tmp_path / "auth.json"
    for document in ({}, {"tokens": []}, {"tokens": {"account_id": " "}}):
        auth.write_text(json.dumps(document))
        auth.chmod(0o600)
        assert identity.codex_account_key(auth_file=auth) is None


def test_process_environment_and_session_account_fallbacks(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "proc"
    process = root / "9"
    process.mkdir(parents=True)
    (process / "environ").write_bytes(b"CODEX_HOME=/odd/profile\0BROKEN\0")
    monkeypatch.setattr(
        identity,
        "Path",
        lambda value="": root if value == "/proc" else Path(value),
    )
    # Exercise the reader separately; session profile behavior uses a direct fake.
    assert identity._process_environment_value(9, "CODEX_HOME") == "/odd/profile"
    assert identity._process_environment_value(9, "MISSING") is None
    monkeypatch.setattr(identity, "_process_environment_value", lambda *_: "/odd/profile")
    monkeypatch.setattr(identity, "codex_email", lambda **_: None)
    account = identity.codex_session_account(9)
    assert account.label() == "codex-profile"
    assert identity.session_account("other", 9).email == "unavailable"
    monkeypatch.setattr(identity, "claude_email", lambda: "person@example.com")
    assert identity.session_account("claude", 9).label() == "claude · person@example.com"


def test_claude_identity_handles_missing_cli_and_transport_failures(monkeypatch) -> None:
    monkeypatch.setattr(identity.shutil, "which", lambda _: None)
    assert identity.claude_email() is None
    monkeypatch.setattr(identity.shutil, "which", lambda _: "/bin/claude")
    monkeypatch.setattr(
        identity.subprocess,
        "run",
        lambda *a, **k: (_ for _ in ()).throw(subprocess.TimeoutExpired("claude", 1)),
    )
    assert identity.claude_email() is None


def test_proc_readers_fail_closed_on_permissions_and_malformed_stat(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(proc, "PROC", tmp_path)
    monkeypatch.setattr(Path, "read_text", lambda *a, **k: (_ for _ in ()).throw(PermissionError()))
    assert proc.read_comm(2) == ""
    with pytest.raises(proc.ProcessGoneError):
        proc.read_start_time(2)


def test_proc_tty_ppid_children_and_accessors(tmp_path: Path, monkeypatch) -> None:
    pid = tmp_path / "7"
    (pid / "fd").mkdir(parents=True)
    (pid / "status").write_text("Name:\tx\n")
    monkeypatch.setattr(proc, "PROC", tmp_path)
    monkeypatch.setattr(
        proc, "_read_link", lambda path: "/dev/tty2" if path.name == "1" else "pipe:[1]"
    )
    assert proc.read_tty(7) == "tty2"
    assert proc.read_ppid(7) == 0
    assert proc.children(7) == ()
    info = _info()
    assert (info.pid, info.exe, info.tty) == (44, "/usr/bin/tool", "pts/2")


@pytest.mark.parametrize(
    ("changes", "expected"),
    [
        ({"comm": "ssh"}, ProcessClass.SSH),
        ({"environ_keys": frozenset({"SSH_CLIENT"})}, ProcessClass.SSH),
        ({"comm": "screen"}, ProcessClass.SCREEN),
        ({"environ_keys": frozenset({"TMUX_PANE"})}, ProcessClass.TMUX),
        ({"environ_keys": frozenset({"STY"})}, ProcessClass.SCREEN),
        ({"comm": "vim"}, ProcessClass.EDITOR),
        ({"comm": "git"}, ProcessClass.UNKNOWN),
    ],
)
def test_classifier_refuses_unsafe_process_classes(monkeypatch, changes, expected) -> None:
    monkeypatch.setattr(classify, "_CONTAINER_FILES", ())
    verdict = classify.classify(_info(**changes))
    assert verdict.process_class is expected
    assert not verdict.automatable


def test_classifier_detects_ambiguous_agent_evidence(monkeypatch) -> None:
    monkeypatch.setattr(classify, "_CONTAINER_FILES", ())
    ambiguous = _info(
        comm="claude",
        cmdline=("codex",),
        identity=ProcessIdentity(44, 55, "pts/2", "/usr/bin/claude"),
    )
    assert classify.classify(ambiguous).blocker == "ambiguous-provider-evidence"


def test_doctor_failure_and_environment_branches(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(doctor.shutil, "which", lambda _: "/bin/tool")
    monkeypatch.setattr(doctor.subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(OSError()))
    assert doctor._tool_version("tool") == ""
    monkeypatch.setattr(doctor.platform, "system", lambda: "Darwin")
    assert doctor.check_platform().status is doctor.Status.FAIL
    monkeypatch.setattr(doctor.os, "geteuid", lambda: 2)
    monkeypatch.setattr(doctor.os, "getuid", lambda: 1)
    assert doctor.check_privileges().status is doctor.Status.WARN
    monkeypatch.setenv("XDG_CURRENT_DESKTOP", "GNOME")
    assert doctor.check_desktop().status is doctor.Status.WARN
    monkeypatch.setattr(Path, "mkdir", lambda *a, **k: (_ for _ in ()).throw(OSError("no")))
    assert doctor._writable_dir("x", tmp_path / "x").status is doctor.Status.FAIL


@pytest.mark.parametrize(
    ("provider", "document", "detail"),
    [
        ("other", {}, "unsupported-provider"),
        ("openai", [], "malformed-status"),
        ("openai", {}, "missing-components"),
        ("openai", {"components": [4]}, "component-not-found"),
        (
            "openai",
            {
                "components": [
                    {"id": "01KMP3KP5MGE23B80K1EK4S8PV", "name": 4, "status": "operational"}
                ]
            },
            "component-not-found",
        ),
    ],
)
def test_status_parser_malformed_documents(provider, document, detail) -> None:
    health = parse_summary(provider, document, now=datetime.now(UTC))
    assert health.state is HealthState.UNKNOWN
    assert health.detail == detail


def test_status_client_rejects_encoding_http_and_url_errors() -> None:
    class Response:
        status = 200
        headers: ClassVar = {"Content-Encoding": "br"}

        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

        def read(self, _size):
            return b"{}"

    assert (
        StatusPageClient("openai", opener=lambda *a, **k: Response()).fetch().state
        is HealthState.UNKNOWN
    )
    for error in (urllib.error.HTTPError("url", 500, "bad", {}, None), urllib.error.URLError("no")):

        def opener(*_a, error=error, **_k):
            raise error

        assert StatusPageClient("openai", opener=opener).fetch().state is HealthState.UNKNOWN


def test_status_client_handles_non_success_and_cached_304() -> None:
    class Response:
        headers: ClassVar = {}

        def __init__(self, status: int) -> None:
            self.status = status

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self, _size):
            return b""

    unavailable = StatusPageClient("openai", opener=lambda *a, **k: Response(503))
    assert unavailable.fetch().detail == "status-unreachable"
    cached = StatusPageClient("openai", opener=lambda *a, **k: Response(304))
    cached._cached = ProviderHealth("openai", HealthState.ONLINE, "cached")
    assert cached.fetch().detail == "cached"


def test_health_monitor_thread_lifecycle_and_idempotent_start() -> None:
    calls: list[str] = []

    def fetch(provider: str) -> ProviderHealth:
        calls.append(provider)
        return ProviderHealth(provider, HealthState.ONLINE, "ok")

    monitor = HealthMonitor(interval=0, fetch=fetch)
    monitor.start()
    threads = tuple(monitor._threads)
    monitor.start()
    assert tuple(monitor._threads) == threads
    deadline = time.monotonic() + 1
    while len(calls) < 2 and time.monotonic() < deadline:
        time.sleep(0.001)
    monitor.stop()
    assert set(calls) == {"openai", "anthropic"}
