# SPDX-FileCopyrightText: 2026 Marcel Petrick
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The last moments before a keystroke, one changed fact at a time.

A tick reads the process table four times on the way to ``sendText``: the
observation, the revalidation in ``act``, the final observation after the
intent is persisted, and the final bare identity read. Each test changes the
world at exactly one of those reads and checks that nothing is typed and that
the persisted intent is settled rather than left dangling.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field, replace
from pathlib import Path

import pytest

from agent_while_true.config import Config, Mode
from agent_while_true.fsm import SystemInspector, observe_only
from agent_while_true.proc import ProcessIdentity, ProcessInfo
from agent_while_true.states import ActionState, SessionState
from agent_while_true.terminal.base import TerminalUnavailableError
from tests import harness as harness_module
from tests import screens
from tests.test_fsm import PID, SESSION, _claude_session

Rewrite = Callable[[ProcessInfo | None], ProcessInfo | None]


@dataclass(slots=True)
class ScriptedInspector:
    """Delegates to the fake process table, rewriting chosen ``inspect`` calls."""

    inner: harness_module.FakeInspector
    script: dict[int, Rewrite] = field(default_factory=dict)
    calls: int = 0

    def inspect(self, pid: int) -> ProcessInfo | None:
        self.calls += 1
        info = self.inner.inspect(pid)
        rewrite = self.script.get(self.calls)
        return rewrite(info) if rewrite else info

    def identify(self, pid: int) -> ProcessIdentity | None:
        return self.inner.identify(pid)


def _scripted(kit, script: dict[int, Rewrite]) -> ScriptedInspector:
    scripted = ScriptedInspector(kit.inspector, script)
    kit.supervisor.inspector = scripted
    return scripted


def _session(kit):
    return kit.supervisor.sessions[kit.terminal.ref(SESSION).key()]


def _as_shell(info):
    return replace(
        info, comm="zsh", cmdline=("zsh",), identity=replace(info.identity, exe="/bin/zsh")
    )


def _under_tmux(info):
    return replace(info, environ_keys=info.environ_keys | {"TMUX"})


def _other_process(info):
    return replace(info, identity=replace(info.identity, start_time=info.identity.start_time + 1))


@pytest.mark.parametrize(
    ("call", "rewrite", "reason"),
    [
        (3, _as_shell, "revalidation-failed:process-gone"),
        (4, lambda info: None, "revalidation-failed:process-identity-changed"),
        (4, _other_process, "revalidation-failed:process-identity-changed"),
        (4, _under_tmux, "revalidation-failed:process-classification-changed"),
    ],
)
def test_a_change_at_the_final_reads_cancels_and_settles(
    tmp_path: Path, call: int, rewrite: Rewrite, reason: str
) -> None:
    kit, _ = _claude_session(tmp_path)
    _scripted(kit, {call: rewrite})
    decision = kit.supervisor.tick()[0]
    assert decision.reason == reason
    assert kit.sent == []
    record = kit.supervisor.store.records[_session(kit).pending_key]
    assert record.state is ActionState.FAILED


def test_an_unreadable_terminal_at_the_final_read_cancels(tmp_path: Path) -> None:
    kit, _ = _claude_session(tmp_path)
    real = kit.terminal.foreground_pid
    calls = {"n": 0}

    def flaky(ref):
        calls["n"] += 1
        if calls["n"] == 4:
            raise TerminalUnavailableError("bus hiccup")
        return real(ref)

    kit.supervisor.terminal = _Flaky(kit.terminal, flaky)
    decision = kit.supervisor.tick()[0]
    assert decision.reason == "revalidation-failed:process-identity-changed"
    assert kit.sent == []


@dataclass(slots=True)
class _Flaky:
    """A terminal whose foreground PID read can be replaced."""

    inner: object
    foreground: Callable

    def __getattr__(self, name: str):
        return getattr(self.inner, name)

    def foreground_pid(self, ref):
        return self.foreground(ref)


def _change_screen_at(kit, read: int, lines: list[str]) -> None:
    reads = {"n": 0}

    def hook(session_id: str) -> None:
        reads["n"] += 1
        if reads["n"] == read:
            kit.terminal.set_screen(session_id, lines)

    kit.terminal.after_read = hook


def test_a_new_prompt_before_revalidation_cancels(tmp_path: Path) -> None:
    kit, _ = _claude_session(tmp_path)
    _change_screen_at(kit, 1, [*screens.CLAUDE_READY_TO_RESUME, "  another line"])
    assert kit.supervisor.tick()[0].reason == "revalidation-failed:prompt-changed"
    assert kit.sent == []


def test_a_new_prompt_after_the_intent_is_persisted_cancels(tmp_path: Path) -> None:
    kit, _ = _claude_session(tmp_path)
    _change_screen_at(kit, 2, [*screens.CLAUDE_READY_TO_RESUME, "  another line"])
    assert kit.supervisor.tick()[0].reason == "revalidation-failed:prompt-changed"
    assert kit.sent == []
    record = kit.supervisor.store.records[_session(kit).pending_key]
    assert record.state is ActionState.FAILED


def test_verification_in_observe_mode_leaves_the_record_alone(tmp_path: Path) -> None:
    kit, _ = _claude_session(tmp_path)
    kit.supervisor.tick()
    key = _session(kit).pending_key
    kit.supervisor.config = replace(kit.supervisor.config, mode=Mode.OBSERVE)
    kit.clock.advance(10)
    assert kit.supervisor.tick()[0].reason == "observe-mode"
    assert kit.supervisor.store.records[key].state is ActionState.SENT


def test_an_agent_that_exits_before_verification_fails_the_record(tmp_path: Path) -> None:
    kit, _ = _claude_session(tmp_path)
    kit.supervisor.tick()
    key = _session(kit).pending_key
    shell = kit.inspector.add_shell(PID + 1)
    kit.terminal.set_foreground(SESSION, shell.identity.pid)
    kit.clock.advance(10)
    assert kit.supervisor.tick()[0].reason == "verify:process-gone"
    assert kit.supervisor.store.records[key].state is ActionState.FAILED
    assert _session(kit).state is SessionState.PROCESS_GONE


def test_unreadable_terminal_facts_are_observed_as_nothing(tmp_path: Path) -> None:
    kit, ref = _claude_session(tmp_path, screen=list(screens.CLAUDE_ACTIVE))

    def broken(*args, **kwargs):
        raise TerminalUnavailableError("gone")

    kit.supervisor.terminal = _Flaky(kit.terminal, broken)
    assert kit.supervisor.observe(ref).identity is None

    class NoScreen(_Flaky):
        def read_visible_text(self, ref, lines=40):
            raise TerminalUnavailableError("gone")

    kit.supervisor.terminal = NoScreen(kit.terminal, kit.terminal.foreground_pid)
    observation = kit.supervisor.observe(ref)
    # An unreadable screen is an empty one: nothing on it can be recognised.
    assert observation.recognition is not None
    assert observation.recognition.matches == ()


def test_a_process_that_vanished_between_reads_is_gone(tmp_path: Path) -> None:
    kit, ref = _claude_session(tmp_path, screen=list(screens.CLAUDE_ACTIVE))
    kit.inspector.remove(PID)
    observation = kit.supervisor.observe(ref)
    assert observation.identity is None
    assert observation.quota.note == "process-gone"


def test_a_provider_without_a_quota_source_is_unknown(tmp_path: Path) -> None:
    kit, ref = _claude_session(tmp_path, screen=list(screens.CLAUDE_ACTIVE))
    kit.supervisor.quota_sources.pop("claude")
    assert kit.supervisor.observe(ref).quota.note == "no-source-configured"


def test_rediscovery_survives_an_unreachable_terminal(tmp_path: Path) -> None:
    kit, _ = _claude_session(tmp_path, screen=list(screens.CLAUDE_ACTIVE))
    kit.terminal.available = False
    kit.supervisor.prune_and_rebind()
    assert len(kit.supervisor.sessions) == 1
    kit.terminal.available = True
    kit.supervisor.prune_and_rebind()
    assert len(kit.supervisor.sessions) == 1
    assert "event=rediscovery_failed" in (tmp_path / "agent-while-true.log").read_text()


def test_selection_housekeeping(tmp_path: Path) -> None:
    kit, ref = _claude_session(tmp_path, screen=list(screens.CLAUDE_ACTIVE))
    kit.supervisor.mark_unsafe("no-such-session", "test")
    kit.supervisor.deselect(ref.key())
    assert kit.supervisor.sessions == {}
    assert observe_only(Config(mode=Mode.OBSERVE))
    assert not observe_only(Config(mode=Mode.AUTO))


def test_the_system_inspector_reads_this_process_and_nothing_gone() -> None:
    import os

    inspector = SystemInspector()
    assert inspector.inspect(os.getpid()) is not None
    assert inspector.identify(os.getpid()) is not None
    assert inspector.inspect(2**22 + 12345) is None
    assert inspector.identify(2**22 + 12345) is None
