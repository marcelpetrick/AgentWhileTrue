# SPDX-FileCopyrightText: 2026 Marcel Petrick
# SPDX-License-Identifier: GPL-3.0-or-later

"""Discovery operation counts, without weakening fresh process inspection."""

import io
import subprocess

import pytest

from agent_while_true import cli
from agent_while_true.config import Config
from agent_while_true.picker import discover
from agent_while_true.terminal.base import TerminalAdapter, TerminalUnavailableError
from agent_while_true.terminal.fake import FakeAdapter
from agent_while_true.terminal.konsole import KonsoleAdapter
from tests.harness import FakeInspector, ScriptedQuota
from tests.test_terminal import StubbedKonsole


class CountingKonsole(StubbedKonsole):
    def __init__(self) -> None:
        super().__init__(qdbus="/usr/bin/qdbus6")
        self.calls: list[tuple[str, ...]] = []

    def _call(self, *args: str) -> str | None:
        self.calls.append(args)
        return super()._call(*args)


@pytest.mark.parametrize("command", [cli.command_status, cli.command_quota])
def test_text_diagnostics_do_not_fetch_unused_titles(tmp_path, monkeypatch, command) -> None:
    terminal = FakeAdapter()
    inspector = FakeInspector()
    info = inspector.add_claude(15102)
    terminal.add("/Sessions/1", shell_pid=100, foreground_pid=info.pid, title="unused")
    brief_calls = []
    original = FakeAdapter.list_sessions_brief

    def brief(self):
        brief_calls.append(True)
        return original(self)

    def full(self):
        pytest.fail("text diagnostics fetched unused titles")

    monkeypatch.setattr(FakeAdapter, "list_sessions", full)
    monkeypatch.setattr(FakeAdapter, "list_sessions_brief", brief)
    monkeypatch.setattr(cli, "KonsoleAdapter", lambda: terminal)
    monkeypatch.setattr(cli, "SystemInspector", lambda: inspector)
    monkeypatch.setattr(cli, "default_sources", lambda path: {"claude": ScriptedQuota()})
    assert command(Config(state_dir=tmp_path), io.StringIO()) == 0
    assert brief_calls == [True]
    assert not terminal.sent


def test_brief_enumeration_skips_only_title_calls() -> None:
    adapter = CountingKonsole()
    complete = adapter.list_sessions()
    complete_calls = list(adapter.calls)
    adapter.calls.clear()

    brief = adapter.list_sessions_brief()

    title_call = (
        "org.kde.konsole-4452",
        "/Sessions/1",
        "org.kde.konsole.Session.title",
        "1",
    )
    assert title_call in complete_calls
    assert adapter.calls == [call for call in complete_calls if call != title_call]
    assert len(brief) == len(complete) == 1
    assert brief[0].ref == complete[0].ref
    assert brief[0].shell_pid == complete[0].shell_pid
    assert brief[0].foreground_pid == complete[0].foreground_pid
    assert brief[0].title == ""


def test_discovery_without_titles_reinspects_processes() -> None:
    terminal = FakeAdapter()
    inspector = FakeInspector()
    first = inspector.add_claude(15102)
    ref = terminal.add(
        "/Sessions/1", shell_pid=100, foreground_pid=first.pid, title="optional display title"
    )
    assert discover(terminal, inspector)[0].session.title == "optional display title"
    initial = discover(terminal, inspector, include_titles=False)[0]
    assert initial.session.title == ""
    assert initial.info == first
    assert initial.eligible

    replacement = inspector.add_shell(15103)
    terminal.set_foreground(ref.session_id, replacement.pid)
    replaced = discover(terminal, inspector, include_titles=False)[0]
    assert replaced.info == replacement
    assert replaced.session.foreground_pid == replacement.pid
    assert not replaced.eligible
    assert terminal.sent == []


def test_default_discovery_keeps_titles_and_titleless_path_avoids_them() -> None:
    adapter = CountingKonsole()
    inspector = FakeInspector()
    inspector.add_claude(61811)
    assert discover(adapter, inspector)[0].session.title == "beta : claude"
    adapter.calls.clear()

    assert discover(adapter, inspector, include_titles=False)[0].session.title == ""
    assert not any("org.kde.konsole.Session.title" in call for call in adapter.calls)
    assert any("org.kde.konsole.Session.foregroundProcessId" in call for call in adapter.calls)


def test_brief_base_fallback_preserves_legacy_no_argument_adapter() -> None:
    class LegacyAdapter(FakeAdapter):
        # A pre-optimization adapter need not add an optional keyword to its
        # existing enumeration method in order to remain usable.
        list_sessions_brief = TerminalAdapter.list_sessions_brief

    terminal = LegacyAdapter()
    inspector = FakeInspector()
    info = inspector.add_claude(15102)
    terminal.add("/Sessions/1", shell_pid=100, foreground_pid=info.pid, title="legacy")
    found = discover(terminal, inspector, include_titles=False)
    assert len(found) == 1
    assert found[0].eligible
    assert found[0].session.title == "legacy"


@pytest.mark.parametrize("count", [1, 9, 30])
def test_brief_enumeration_saves_one_subprocess_per_live_tab(monkeypatch, count: int) -> None:
    calls: list[tuple[str, ...]] = []

    def run(args, **kwargs):
        calls.append(tuple(args[1:]))
        match args[1:]:
            case []:
                result = "org.kde.konsole-4452\n"
            case ["org.kde.konsole-4452"]:
                result = "\n".join(f"/Sessions/{index}" for index in range(1, count + 1))
            case [_, _, "org.kde.konsole.Session.processId"]:
                result = "100"
            case [_, _, "org.kde.konsole.Session.foregroundProcessId"]:
                result = "15102"
            case [_, _, "org.kde.konsole.Session.title", "1"]:
                result = "display only"
            case _:
                raise AssertionError("Unexpected discovery RPC")
        return subprocess.CompletedProcess(args, 0, result, "")

    monkeypatch.setattr(subprocess, "run", run)
    terminal = KonsoleAdapter(qdbus="/usr/bin/qdbus6")
    assert len(terminal.list_sessions()) == count
    assert len(calls) == 2 + 3 * count
    calls.clear()
    assert len(terminal.list_sessions_brief()) == count
    assert len(calls) == 2 + 2 * count
    assert sum("org.kde.konsole.Session.foregroundProcessId" in call for call in calls) == count


def test_brief_fake_preserves_unavailable_and_closed_tab_behavior() -> None:
    terminal = FakeAdapter()
    terminal.add("/Sessions/1", shell_pid=100, foreground_pid=15102, title="not needed")
    terminal.close("/Sessions/1")
    assert terminal.list_sessions_brief() == []
    terminal.available = False
    with pytest.raises(TerminalUnavailableError):
        terminal.list_sessions_brief()
    assert discover(terminal, FakeInspector(), include_titles=False) == []
