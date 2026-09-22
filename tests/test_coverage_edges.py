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

from agent_while_true import classify, doctor, identity, proc
from agent_while_true.classify import ProcessClass
from agent_while_true.proc import ProcessIdentity, ProcessInfo
from agent_while_true.service_health import (
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
    monkeypatch.setattr(identity, "claude_email", lambda **_: "person@example.com")
    claude = identity.session_account("claude", 9)
    assert claude.label() == "claude-profile · person@example.com"


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


# -- configuration, /proc, preferences, identity and logging edges ----------


@pytest.mark.parametrize(
    ("key", "value", "message"),
    [
        ("MAX_RESUME_ATTEMPTS", "many", "cannot parse integer"),
        ("MODE", "yolo", "unknown mode"),
    ],
)
def test_bad_configuration_values_are_named(key: str, value: str, message: str) -> None:
    from agent_while_true.config import ConfigError, load

    with pytest.raises(ConfigError, match=message):
        load(config_path=Path("/nonexistent"), environ={}, overrides={key: value})


def test_prefixed_environment_names_outside_the_schema_are_ignored() -> None:
    from agent_while_true.config import load

    config = load(
        config_path=Path("/nonexistent"),
        environ={"AGENT_WHILE_TRUE_NOT_A_KEY": "1", "AGENT_WHILE_TRUE_MODE": "ask"},
    )
    assert config.mode.value == "ask"


def test_proc_reads_fail_in_the_expected_direction(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(proc, "PROC", tmp_path)
    (tmp_path / "5").mkdir()
    (tmp_path / "5" / "stat").write_text("5 (x) S 1 2 3")
    with pytest.raises(proc.ProcessGoneError, match="truncated"):
        proc.read_start_time(5)
    assert proc.exists(5)
    assert not proc.exists(6)
    # A vanished link is a vanished process; an unreadable one is merely unknown.
    with pytest.raises(proc.ProcessGoneError):
        proc._read_link(tmp_path / "5" / "exe")
    (tmp_path / "5" / "cwd").write_text("")
    assert proc._read_link(tmp_path / "5" / "cwd") == ""


@pytest.mark.parametrize(
    "document",
    [
        {"theme": "neon"},
        {"show_events": "yes"},
    ],
)
def test_preferences_with_an_invalid_field_are_ignored(document: dict) -> None:
    from agent_while_true.preferences import PREFERENCES_VERSION, _validated_values

    base = {
        "version": PREFERENCES_VERSION,
        "theme": "dark",
        "history_length": 10,
        "show_events": True,
        "details_visible": False,
        "help_visible": False,
    }
    assert _validated_values(base) is not None
    assert _validated_values({**base, **document}) is None


def test_oversized_preferences_are_not_read(tmp_path: Path) -> None:
    from agent_while_true.preferences import MAX_PREFERENCES_BYTES, _current_document

    path = tmp_path / "preferences.json"
    path.write_text(" " * (MAX_PREFERENCES_BYTES + 1))
    assert _current_document(path) is None


def test_codex_identity_rejects_documents_without_usable_tokens(tmp_path: Path) -> None:
    auth = tmp_path / "auth.json"
    for document in ([1, 2], {"tokens": "x"}):
        auth.write_text(json.dumps(document))
        auth.chmod(0o600)
        assert identity.codex_email(auth_file=auth) is None
        assert identity.codex_account_key(auth_file=auth) is None


def test_a_vanished_process_has_no_environment_value() -> None:
    assert identity._process_environment_value(2**22 + 12345, "CODEX_HOME") is None


def test_an_unusual_codex_home_reads_as_a_generic_profile(monkeypatch) -> None:
    monkeypatch.setattr(identity, "_process_environment_value", lambda pid, key: "/srv/odd home")
    monkeypatch.setattr(identity, "codex_email", lambda **kwargs: None)
    assert identity.codex_session_account(1).profile == "codex-profile"


def test_an_unknown_provider_has_no_account() -> None:
    account = identity.session_account("gemini", 1)
    assert account.profile == "gemini"
    assert account.email == "unavailable"


def test_log_values_render_compactly(tmp_path: Path) -> None:
    from agent_while_true import logging_setup

    assert (
        logging_setup.format_event("x", {"ratio": 0.5, "whole": 2.0}) == "event=x ratio=0.5 whole=2"
    )
    logger = logging_setup.setup(tmp_path / "a.log", to_stderr=True)
    logger.debug("quiet")
    assert logging_setup.get_logger()._logger is logger._logger
