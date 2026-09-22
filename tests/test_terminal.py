# SPDX-FileCopyrightText: 2026 Marcel Petrick
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for the terminal adapter layer.

The Konsole adapter is tested against a stubbed ``qdbus`` so the suite runs in
CI, where no KDE session exists. A separate opt-in test exercises the real bus.
"""

from __future__ import annotations

import os

import pytest

from agent_while_true.terminal.base import SessionRef, TerminalUnavailableError
from agent_while_true.terminal.fake import FakeAdapter
from agent_while_true.terminal.konsole import KonsoleAdapter

QDBUS_RESPONSES = {
    (): " org.kde.konsole-4452\n org.freedesktop.DBus\n org.kde.konsole\n",
    (
        "org.kde.konsole-4452",
    ): "/\n/MainApplication\n/Sessions\n/Sessions/1\n/Sessions/2\n/Windows\n",
    ("org.kde.konsole-4452", "/Sessions/1", "org.kde.konsole.Session.processId"): "61578\n",
    (
        "org.kde.konsole-4452",
        "/Sessions/1",
        "org.kde.konsole.Session.foregroundProcessId",
    ): "61811\n",
    (
        "org.kde.konsole-4452",
        "/Sessions/1",
        "org.kde.konsole.Session.title",
        "1",
    ): "beta : claude\n",
    ("org.kde.konsole-4452", "/Sessions/2", "org.kde.konsole.Session.processId"): "0\n",
    (
        "org.kde.konsole-4452",
        "/Sessions/1",
        "org.kde.konsole.Session.getAllDisplayedTextList",
        "true",
    ): "one\ntwo\nthree\nfour\n",
    (
        "org.kde.konsole-4452",
        "/Sessions/1",
        "org.kde.konsole.Session.sendText",
        "",
    ): "",
}


class StubbedKonsole(KonsoleAdapter):
    """Konsole adapter with the qdbus round trip replaced by a lookup table."""

    def _call(self, *args: str):  # type: ignore[override]
        return QDBUS_RESPONSES.get(tuple(args))


def test_services_ignores_non_konsole_names() -> None:
    adapter = StubbedKonsole(qdbus="/usr/bin/qdbus6")
    assert adapter.services() == ["org.kde.konsole-4452", "org.kde.konsole"]


def test_list_sessions_skips_a_tab_that_closed_mid_scan() -> None:
    adapter = StubbedKonsole(qdbus="/usr/bin/qdbus6")
    sessions = adapter.list_sessions()
    assert len(sessions) == 1
    only = sessions[0]
    assert only.shell_pid == 61578
    assert only.foreground_pid == 61811
    assert only.title == "beta : claude"
    assert only.ref.key() == "konsole/org.kde.konsole-4452/Sessions/1"


def test_read_visible_text_is_bounded_to_the_tail() -> None:
    adapter = StubbedKonsole(qdbus="/usr/bin/qdbus6")
    ref = SessionRef("konsole", "org.kde.konsole-4452", "/Sessions/1")
    assert adapter.read_visible_text(ref, lines=2) == ["three", "four"]


def test_missing_qdbus_reports_unavailable_rather_than_crashing() -> None:
    adapter = KonsoleAdapter(qdbus=None)
    assert not adapter.is_available()
    with pytest.raises(TerminalUnavailableError):
        adapter.services()


def test_failed_send_raises() -> None:
    adapter = StubbedKonsole(qdbus="/usr/bin/qdbus6")
    ref = SessionRef("konsole", "org.kde.konsole-4452", "/Sessions/1")
    with pytest.raises(TerminalUnavailableError):
        adapter.send_text(ref, "\r")


def test_fake_adapter_records_what_was_sent() -> None:
    adapter = FakeAdapter()
    ref = adapter.add("/Sessions/1", shell_pid=100, foreground_pid=200, screen=["hello"])
    adapter.send_text(ref, "\r")
    assert adapter.sent == [("/Sessions/1", "\r")]


def test_fake_adapter_models_a_closed_tab() -> None:
    adapter = FakeAdapter()
    ref = adapter.add("/Sessions/1", shell_pid=100, foreground_pid=200)
    adapter.close("/Sessions/1")
    assert adapter.list_sessions() == []
    assert adapter.foreground_pid(ref) == 0
    assert adapter.read_visible_text(ref) == []
    with pytest.raises(TerminalUnavailableError):
        adapter.send_text(ref, "\r")


@pytest.mark.konsole
@pytest.mark.skipif(
    not os.environ.get("AGENT_WHILE_TRUE_LIVE_KONSOLE"),
    reason="set AGENT_WHILE_TRUE_LIVE_KONSOLE=1 to exercise the real D-Bus interface",
)
def test_live_konsole_enumeration() -> None:
    adapter = KonsoleAdapter()
    assert adapter.is_available()
    for session in adapter.list_sessions():
        assert session.shell_pid > 0


# -- the real qdbus round trip, against a stand-in executable ---------------


def _fake_qdbus(tmp_path, body: str):
    script = tmp_path / "qdbus6"
    script.write_text(f"#!/bin/sh\n{body}\n")
    script.chmod(0o755)
    return str(script)


def test_find_qdbus_prefers_the_first_installed_candidate(monkeypatch) -> None:
    from agent_while_true.terminal import konsole

    installed = {"qdbus": "/usr/bin/qdbus"}
    monkeypatch.setattr(konsole.shutil, "which", installed.get)
    assert konsole.find_qdbus() == "/usr/bin/qdbus"
    assert KonsoleAdapter().qdbus == "/usr/bin/qdbus"
    monkeypatch.setattr(konsole.shutil, "which", lambda name: None)
    assert konsole.find_qdbus() is None


def test_a_real_call_passes_arguments_without_a_shell(tmp_path) -> None:
    adapter = KonsoleAdapter(qdbus=_fake_qdbus(tmp_path, 'printf "%s|" "$@"'))
    assert adapter._call("svc", "/Sessions/1", "a b; $HOME") == "svc|/Sessions/1|a b; $HOME|"
    assert adapter.is_available()


def test_a_failing_call_is_none_and_every_reader_degrades(tmp_path) -> None:
    adapter = KonsoleAdapter(qdbus=_fake_qdbus(tmp_path, "exit 3"))
    ref = SessionRef("konsole", "org.kde.konsole-1", "/Sessions/1")
    assert adapter._call("x") is None
    assert not adapter.is_available()
    with pytest.raises(TerminalUnavailableError):
        adapter.services()
    assert adapter._session_paths("org.kde.konsole-1") == []
    assert adapter.foreground_pid(ref) == 0
    assert adapter.read_visible_text(ref) == []


def test_an_unstartable_qdbus_is_a_failed_call(tmp_path) -> None:
    adapter = KonsoleAdapter(qdbus=str(tmp_path / "missing"))
    assert adapter._call() is None


def test_a_non_numeric_pid_reads_as_zero(tmp_path) -> None:
    adapter = KonsoleAdapter(qdbus=_fake_qdbus(tmp_path, "echo not-a-pid"))
    ref = SessionRef("konsole", "org.kde.konsole-1", "/Sessions/1")
    assert adapter.foreground_pid(ref) == 0
