# SPDX-FileCopyrightText: 2026 Marcel Petrick
# SPDX-License-Identifier: GPL-3.0-or-later

"""A bounded transport reread recovers the recognizer's existing frame grammar.

The long frame below is a synthetic boundary construction derived from the
captured ordinary Yes/No prompt. It is not a new live capture or evidence that
any historical unsupported appearance had this exact shape.
"""

from dataclasses import replace

import pytest

from agent_while_true import fsm
from agent_while_true.config import Mode
from agent_while_true.fsm import CLAUDE_APPROVAL_CAPTURE_ROWS
from agent_while_true.providers import CLAUDE
from agent_while_true.states import SessionState
from agent_while_true.terminal.base import TerminalUnavailableError
from tests import harness, screens


def _long_existing_frame() -> list[str]:
    # The solid rule is 39 rows above the question: within the existing
    # recognizer's 40-row bound, but outside the normal 40-row transport tail.
    return list(screens.CLAUDE_APPROVAL_CAPTURE_BOUNDARY)


class RecordingTerminal:
    def __init__(self, inner):
        self.inner = inner
        self.reads = []
        self.fail_at = 0
        self.empty_at = 0
        self.foreground_calls = 0
        self.fail_foreground_at = 0

    def __getattr__(self, name):
        return getattr(self.inner, name)

    def read_visible_text(self, ref, lines=40):
        self.reads.append(lines)
        if len(self.reads) == self.fail_at:
            raise TerminalUnavailableError("synthetic capture failure")
        if len(self.reads) == self.empty_at:
            return []
        return self.inner.read_visible_text(ref, lines)

    def foreground_pid(self, ref):
        self.foreground_calls += 1
        if self.foreground_calls == self.fail_foreground_at:
            raise TerminalUnavailableError("synthetic foreground failure")
        return self.inner.foreground_pid(ref)


def _kit(tmp_path, screen=None, *, visible_lines=40):
    kit = harness.build(tmp_path)
    kit.supervisor.config = replace(kit.supervisor.config, visible_lines=visible_lines)
    info = kit.inspector.add_claude(4101)
    ref = kit.terminal.add(
        "/Sessions/1",
        shell_pid=100,
        foreground_pid=info.pid,
        screen=_long_existing_frame() if screen is None else screen,
    )
    kit.supervisor.select(ref, info.identity, "claude", "synthetic boundary")
    terminal = RecordingTerminal(kit.terminal)
    kit.supervisor.terminal = terminal
    return kit, ref, terminal


def test_existing_exact_grammar_is_not_lost_at_transport_tail(tmp_path):
    kit, ref, terminal = _kit(tmp_path)
    frame = _long_existing_frame()
    assert CLAUDE.recognise(frame, now=kit.clock.now()).approval_prompt
    assert not CLAUDE.recognise(frame[-40:], now=kit.clock.now()).approval_prompt
    observed = kit.supervisor.observe(ref)
    assert observed.recognition.approval_prompt
    assert terminal.reads == [40, CLAUDE_APPROVAL_CAPTURE_ROWS]
    assert not kit.sent


@pytest.mark.parametrize("visible_lines", [40, 80, 100])
def test_bounded_capture_does_not_repeat_an_already_sufficient_read(tmp_path, visible_lines):
    kit, ref, terminal = _kit(tmp_path, visible_lines=visible_lines)
    assert kit.supervisor.observe(ref).recognition.approval_prompt
    assert terminal.reads == (
        [40, CLAUDE_APPROVAL_CAPTURE_ROWS] if visible_lines == 40 else [visible_lines]
    )


@pytest.mark.parametrize("screen", [screens.CLAUDE_APPROVAL_YES_NO, screens.CLAUDE_IDLE_COMPOSER])
def test_normal_exact_or_active_screens_need_only_one_read(tmp_path, screen):
    kit, ref, terminal = _kit(tmp_path, screen=screen)
    kit.supervisor.observe(ref)
    assert terminal.reads == [40]


@pytest.mark.parametrize("failure", ["exception", "empty"])
def test_failed_expansion_never_falls_back_to_the_partial_prompt(tmp_path, failure):
    kit, ref, terminal = _kit(tmp_path)
    if failure == "exception":
        terminal.fail_at = 2
    else:
        terminal.empty_at = 2
    observed = kit.supervisor.observe(ref)
    assert observed.recognition is None
    assert not observed.screen_read
    assert not kit.sent


@pytest.mark.parametrize("replacement", ["active", "draft", "model", "paid", "different-command"])
def test_expanded_read_replaces_the_entire_prompt_and_veto_context(tmp_path, replacement):
    kit, ref, terminal = _kit(tmp_path)
    old = CLAUDE.recognise(_long_existing_frame(), now=kit.clock.now())
    if replacement == "active":
        screen = list(screens.CLAUDE_IDLE_COMPOSER)
    elif replacement == "draft":
        glyph = "\N{HEAVY RIGHT-POINTING ANGLE QUOTATION MARK ORNAMENT}"
        screen = [
            line.replace(f"{glyph} ", f"{glyph} synthetic draft")
            for line in screens.CLAUDE_IDLE_COMPOSER
        ]
    else:
        screen = _long_existing_frame()
        if replacement == "different-command":
            screen = [line.replace("head -30", "head -31") for line in screen]
        else:
            screen.insert(
                -5,
                "Switch to another model"
                if replacement == "model"
                else "Run /usage-credits to continue now",
            )

    def change(session_id):
        if len(terminal.reads) == 1:
            kit.terminal.set_screen(session_id, screen)

    kit.terminal.after_read = change
    observed = kit.supervisor.observe(ref)
    expected = CLAUDE.recognise(screen, now=kit.clock.now())
    assert observed.recognition == expected
    if replacement in {"model", "paid"}:
        assert observed.recognition.vetoes
    elif replacement == "different-command":
        assert observed.recognition.approval_fingerprint != old.approval_fingerprint
    else:
        assert observed.recognition.state is SessionState.ACTIVE
        assert not observed.recognition.approval_prompt
        if replacement == "draft":
            assert not observed.recognition.composer_empty
    assert not kit.sent


@pytest.mark.parametrize("drift", ["shell", "start", "classification", "gone", "bus-failure"])
def test_identity_or_classification_drift_during_expansion_fails_closed(tmp_path, drift):
    kit, ref, terminal = _kit(tmp_path)

    def change(session_id):
        if len(terminal.reads) != 2:
            return
        if drift == "shell":
            shell = kit.inspector.add_shell(4200)
            kit.terminal.set_foreground(session_id, shell.pid)
        elif drift == "start":
            kit.inspector.add_claude(4101, start_time=999)
        elif drift == "classification":
            info = kit.inspector.processes[4101]
            kit.inspector.processes[4101] = replace(info, environ_keys=frozenset({"TMUX"}))
        elif drift == "gone":
            kit.inspector.remove(4101)
        else:
            kit.terminal.close(session_id)

    kit.terminal.after_read = change
    observed = kit.supervisor.observe(ref)
    assert observed.identity is None
    assert observed.recognition is None
    assert not observed.screen_read
    assert observed.quota.availability.value == "UNKNOWN"
    assert not kit.sent


def test_codex_does_not_get_claude_capture_fallback(tmp_path):
    kit, ref, terminal = _kit(tmp_path, screen=screens.CODEX_APPROVAL_EXEC_CLIPPED_TITLE_0_162_1)
    info = kit.inspector.add_codex(4201)
    kit.terminal.set_foreground(ref.session_id, info.pid)
    kit.supervisor.observe(ref)
    assert terminal.reads == [40]


def test_expansion_is_bounded_and_does_not_relax_unknown_menu_grammar(tmp_path):
    kit, ref, terminal = _kit(tmp_path, screen=screens.CLAUDE_APPROVAL_CURSOR_ON_TWO)
    observed = kit.supervisor.observe(ref)
    assert not observed.recognition.approval_prompt
    assert terminal.reads == [40, CLAUDE_APPROVAL_CAPTURE_ROWS]
    assert not kit.sent


def test_failure_of_the_post_capture_foreground_read_fails_closed(tmp_path):
    kit, ref, terminal = _kit(tmp_path)
    terminal.fail_foreground_at = 2
    observed = kit.supervisor.observe(ref)
    assert observed.identity is None
    assert observed.recognition is None
    assert not kit.sent


@pytest.mark.parametrize("phase", ["inspect", "classify"])
def test_process_disappearing_during_post_capture_checks_fails_closed(tmp_path, monkeypatch, phase):
    kit, ref, _terminal = _kit(tmp_path)
    if phase == "inspect":
        original = type(kit.inspector).inspect

        def target(self, pid):
            return original(self, pid)

        owner = type(kit.inspector)
        attribute = "inspect"
    else:
        target = fsm.classify
        owner = fsm
        attribute = "classify"
    calls = 0

    def gone(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("synthetic process vanished")
        return target(*args, **kwargs)

    monkeypatch.setattr(owner, attribute, gone)
    observed = kit.supervisor.observe(ref)
    assert observed.identity is None
    assert observed.recognition is None
    assert not kit.sent


@pytest.mark.parametrize("mode", [Mode.OBSERVE, Mode.ASK])
def test_capture_recovery_does_not_bypass_operator_mode(tmp_path, mode):
    kit, ref, _terminal = _kit(tmp_path)
    kit.supervisor.config = replace(kit.supervisor.config, mode=mode)
    kit.supervisor.tick()
    assert kit.supervisor.sessions[ref.key()].approval_exact
    assert kit.supervisor.approve_pending() == {}
    assert not kit.sent


def test_capture_recovery_keeps_once_only_and_claude_one_resend_policy(tmp_path):
    kit, ref, _terminal = _kit(tmp_path)
    kit.supervisor.tick()
    assert kit.supervisor.approve_pending() == {ref.key(): "approved"}
    kit.supervisor.tick()
    assert kit.supervisor.approve_pending() == {}
    kit.clock.advance(3)
    kit.supervisor.tick()
    assert kit.supervisor.approve_pending() == {ref.key(): "resent"}
    kit.clock.advance(3)
    kit.supervisor.tick()
    assert kit.supervisor.approve_pending() == {ref.key(): "unanswered-after-resend"}
    assert kit.sent == [(ref.session_id, "\r"), (ref.session_id, "\r")]
