# SPDX-FileCopyrightText: 2026 Marcel Petrick
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for the terminal adapter layer.

The Konsole adapter is tested against a stubbed ``qdbus`` so the suite runs in
CI, where no KDE session exists. A separate opt-in test exercises the real bus.
"""

import os
from datetime import UTC, datetime

import pytest

from agent_while_true import providers
from agent_while_true.states import SessionState
from agent_while_true.terminal import konsole
from agent_while_true.terminal.base import SessionRef, TerminalUnavailableError
from agent_while_true.terminal.dbus import BusCallError, BusError
from agent_while_true.terminal.fake import FakeAdapter
from agent_while_true.terminal.konsole import KonsoleAdapter
from tests import screens

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
    # Oldest Konsole process first (the unnumbered name sorts as 0), so the
    # dashboard order does not depend on the transport's listing order.
    assert adapter.services() == ["org.kde.konsole", "org.kde.konsole-4452"]


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


def test_blank_padding_below_the_content_does_not_hide_it() -> None:
    """Konsole pads a tall window with blank rows below a short screen.

    Live Claude Code 2.1.283 on 2026-09-28: 88 rows, the permission prompt on
    the top 35, 53 blank rows under it. Keeping the last 40 raw rows kept only
    padding, so the prompt was never seen and auto-yes never fired.
    """
    padded = "\n".join(
        [*screens.CLAUDE_APPROVAL_LIVE_2_1_283, *[""] * screens.KONSOLE_PADDING_ROWS]
    )
    key = (
        "org.kde.konsole-4452",
        "/Sessions/1",
        "org.kde.konsole.Session.getAllDisplayedTextList",
        "true",
    )

    class PaddedKonsole(StubbedKonsole):
        def _call(self, *args: str):  # type: ignore[override]
            return padded + "\n" if tuple(args) == key else super()._call(*args)

    adapter = PaddedKonsole(qdbus="/usr/bin/qdbus6")
    ref = SessionRef("konsole", "org.kde.konsole-4452", "/Sessions/1")

    lines = adapter.read_visible_text(ref, lines=40)

    assert lines == screens.CLAUDE_APPROVAL_LIVE_2_1_283
    recognition = providers.CLAUDE.recognise(lines, now=datetime.now(UTC))
    assert recognition.state is SessionState.APPROVAL_PENDING
    assert recognition.approval_prompt


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


# -- the persistent bus connection for read-only calls ----------------------


class FakeBus:
    """Answers native calls from a table; records them; can fail on demand."""

    def __init__(self, answers: dict[str, object]) -> None:
        self.answers = answers
        self.calls: list[tuple[str, str, str, str, tuple[object, ...]]] = []

    def call(self, destination, path, interface, member, signature="", args=()):
        self.calls.append((destination, path, member, signature, tuple(args)))
        answer = self.answers[member]
        if isinstance(answer, Exception):
            raise answer
        return signature, answer


def _native(tmp_path, answers: dict[str, object], qdbus_body: str = 'printf "qdbus:%s|" "$@"'):
    adapter = KonsoleAdapter(qdbus=_fake_qdbus(tmp_path, qdbus_body))
    adapter.bus = FakeBus(answers)  # type: ignore[assignment]
    return adapter


def test_reads_use_the_bus_connection_and_print_like_qdbus(tmp_path) -> None:
    adapter = _native(
        tmp_path,
        {
            "ListNames": [["org.kde.konsole-9", ":1.4", "org.kde.konsole-3"]],
            "Introspect": ['<node><interface name="x"/><node name="1"/><node name="4"/></node>'],
            "processId": [61578],
            "foregroundProcessId": [61811],
            "title": ["beta : claude"],
            "getAllDisplayedTextList": [["one", "two", "", ""]],
        },
    )
    assert adapter.services() == ["org.kde.konsole-3", "org.kde.konsole-9"]
    assert adapter._session_paths("org.kde.konsole-3") == ["/Sessions/1", "/Sessions/4"]
    ref = SessionRef("konsole", "org.kde.konsole-3", "/Sessions/1")
    assert adapter.foreground_pid(ref) == 61811
    assert adapter.read_visible_text(ref) == ["one", "two"]
    sessions = adapter.list_sessions()
    assert sessions[0].title == "beta : claude"
    assert sessions[0].shell_pid == 61578
    calls = adapter.bus.calls  # type: ignore[union-attr]
    assert ("org.kde.konsole-3", "/Sessions/1", "title", "i", (1,)) in calls
    assert (
        "org.kde.konsole-3",
        "/Sessions/1",
        "getAllDisplayedTextList",
        "b",
        (True,),
    ) in calls
    assert adapter._call("svc") == "/Sessions/1\n/Sessions/4\n"
    assert adapter._call("s", "/Sessions/1", "org.kde.konsole.Session.title", "1") == (
        "beta : claude\n"
    )


def test_typing_never_goes_over_the_bus_connection(tmp_path) -> None:
    adapter = _native(tmp_path, {})
    ref = SessionRef("konsole", "org.kde.konsole-3", "/Sessions/1")
    adapter.send_text(ref, "continue")
    assert adapter.bus.calls == []  # type: ignore[union-attr]
    # Unknown methods and unconvertible arguments also stay with qdbus.
    assert adapter._call("s", "/p", "org.kde.konsole.Session.title", "x").startswith("qdbus:")
    assert adapter._call("s", "/p", "org.kde.konsole.Session.title").startswith("qdbus:")
    assert adapter._call("s", "/p", "org.kde.Other.processId").startswith("qdbus:")
    flag = "org.kde.konsole.Session.getAllDisplayedTextList"
    assert adapter._call("s", "/p", flag, "yes").startswith("qdbus:")
    assert adapter.bus.calls == []  # type: ignore[union-attr]


def test_a_bus_error_reply_is_the_answer_and_a_broken_bus_falls_back(tmp_path) -> None:
    adapter = _native(
        tmp_path,
        {"processId": BusCallError("UnknownObject"), "ListNames": BusError("closed")},
    )
    ref = SessionRef("konsole", "org.kde.konsole-3", "/Sessions/1")
    # No such tab: the same None a failing qdbus gives, without a second try.
    assert adapter._int_call(ref, "processId") == 0
    # A broken connection: this call is answered by qdbus instead.
    assert adapter._call() == "qdbus:|"


@pytest.mark.parametrize(
    "introspection",
    [["<node><unclosed></node>"], [7], []],
)
def test_unusable_introspection_falls_back_to_qdbus(tmp_path, introspection) -> None:
    adapter = _native(tmp_path, {"Introspect": introspection})
    assert adapter._call("svc") == "qdbus:svc|"


def test_an_unexpected_reply_type_falls_back_to_qdbus(tmp_path) -> None:
    adapter = _native(tmp_path, {"processId": [(1, 2)], "title": [True]})
    assert adapter._call("s", "/p", "org.kde.konsole.Session.processId").startswith("qdbus:")
    assert adapter._call("s", "/p", "org.kde.konsole.Session.title", "-1") == "true\n"


def test_only_the_autodetecting_adapter_opens_the_real_bus(monkeypatch) -> None:
    monkeypatch.setenv("DBUS_SESSION_BUS_ADDRESS", "unix:path=/run/user/0/bus")
    monkeypatch.setattr(konsole, "find_qdbus", lambda: "/usr/bin/qdbus6")
    assert KonsoleAdapter().bus is not None
    assert KonsoleAdapter(qdbus="/usr/bin/qdbus6").bus is None
    monkeypatch.setattr(konsole, "find_qdbus", lambda: None)
    assert KonsoleAdapter().bus is None
