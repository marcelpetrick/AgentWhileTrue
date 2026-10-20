# SPDX-FileCopyrightText: 2026 Marcel Petrick
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Approval diagnostics explain missing input without granting permission."""

import os
from pathlib import Path

import pytest

from agent_while_true.config import Mode
from agent_while_true.logging_setup import setup
from agent_while_true.states import ActionState
from agent_while_true.ui import session_details
from agent_while_true.version import __version__
from tests import harness, screens
from tests.pty_dashboard import Dashboard


def _kit(tmp_path: Path, *, exact: bool = True):
    kit = harness.build(tmp_path, mode=Mode.AUTO)
    info = kit.inspector.add_claude(4101)
    ref = kit.terminal.add(
        "/Sessions/1",
        shell_pid=100,
        foreground_pid=info.pid,
        screen=list(
            screens.CLAUDE_APPROVAL_YES_NO if exact else screens.CLAUDE_APPROVAL_CURSOR_ON_TWO
        ),
    )
    kit.supervisor.select(ref, info.identity, "claude", "synthetic permission")
    kit.supervisor.tick()
    return kit, kit.supervisor.sessions[ref.key()]


def test_every_event_has_unspoofable_emitter_identity(tmp_path: Path) -> None:
    log_file = tmp_path / "events.log"
    setup(log_file).info("approval_status", controller_pid=1, controller_version="fake")
    written = log_file.read_text()
    assert f"controller_pid={os.getpid()}" in written
    assert f"controller_version={__version__}" in written
    assert "fake" not in written


@pytest.mark.parametrize(
    ("mode", "enabled", "paused", "owns", "reason"),
    [
        (Mode.AUTO, False, False, True, "auto-yes-off"),
        (Mode.OBSERVE, True, False, False, "observe-mode"),
        (Mode.ASK, True, False, True, "ask-mode-confirms-each"),
        (Mode.AUTO, True, True, True, "dashboard-paused"),
        (Mode.AUTO, True, False, False, "no-input-control"),
        (Mode.AUTO, True, False, True, "eligible-on-next-scan"),
    ],
)
def test_approval_context_explains_each_operator_gate(
    tmp_path: Path, mode: Mode, enabled: bool, paused: bool, owns: bool, reason: str
) -> None:
    from dataclasses import replace

    kit, session = _kit(tmp_path)
    kit.supervisor.config = replace(kit.supervisor.config, mode=mode)
    for _ in range(4):
        kit.supervisor.report_approval_status(auto_yes=enabled, paused=paused, input_control=owns)
    assert session.approval_status == reason
    written = (tmp_path / "agent-while-true.log").read_text()
    assert written.count("event=approval_status ") == 1
    assert f"reason={reason}" in written
    assert f"mode={mode.value}" in written
    assert "controller_pid=" in written
    assert "controller_version=" in written
    assert "pytest" not in written
    assert kit.sent == []


def test_changed_context_and_clearing_are_logged_once(tmp_path: Path) -> None:
    kit, session = _kit(tmp_path)
    kit.supervisor.report_approval_status(auto_yes=False, paused=False, input_control=True)
    kit.supervisor.report_approval_status(auto_yes=True, paused=False, input_control=True)
    kit.terminal.set_screen("/Sessions/1", list(screens.CLAUDE_IDLE_COMPOSER))
    kit.supervisor.tick()
    for _ in range(3):
        kit.supervisor.report_approval_status(auto_yes=True, paused=False, input_control=True)
    assert session.approval_status == "no-pending-approval"
    assert (tmp_path / "agent-while-true.log").read_text().count("event=approval_status ") == 3
    assert kit.sent == []


def test_unsupported_shape_is_visible_even_when_auto_yes_enabled(tmp_path: Path) -> None:
    kit, session = _kit(tmp_path, exact=False)
    kit.supervisor.report_approval_status(auto_yes=True, paused=False, input_control=True)
    assert session.approval_status == "unsupported-permission-layout"
    details = "\n".join(session_details(session, kit.clock.wall, 1))
    assert "Approval automation: unsupported-permission-layout" in details
    assert "stay with same model" in details
    assert "Paid choices: human only" in details
    assert kit.sent == []


@pytest.mark.parametrize(
    "warning",
    ["Switch to another model", "Run /usage-credits to continue now"],
)
def test_exact_box_with_conflicting_context_never_looks_eligible(
    tmp_path: Path, warning: str
) -> None:
    kit, session = _kit(tmp_path)
    screen = list(screens.CLAUDE_APPROVAL_YES_NO)
    screen.insert(2, warning)  # Same current turn, not historical output.
    kit.terminal.set_screen("/Sessions/1", screen)
    kit.supervisor.tick()
    assert session.approval_exact
    assert len(session.matched_ids) == 2
    kit.supervisor.report_approval_status(auto_yes=True, paused=False, input_control=True)
    assert session.approval_status == "conflicting-permission-context"
    assert "conflicting-permission-context" in "\n".join(
        session_details(session, kit.clock.wall, 1)
    )
    assert kit.supervisor.approve_pending()[session.ref.key()] == "no-exact-approval-prompt"
    assert kit.sent == []


@pytest.mark.parametrize("condition", ["unsafe", "verifying", "stuck", "answered"])
def test_cached_session_blockers_do_not_look_eligible(tmp_path: Path, condition: str) -> None:
    kit, session = _kit(tmp_path)
    expected = {
        "unsafe": "session-unsafe",
        "verifying": "action-in-flight",
        "stuck": "unanswered-manual-required",
        "answered": "answered-awaiting-transition",
    }
    if condition == "unsafe":
        session.unsafe_reason = "test"
    elif condition == "verifying":
        session.verify_after = kit.clock.wall
    elif condition == "stuck":
        session.approval_stuck = True
    else:
        session.approved_fingerprint = session.approval_fingerprint
    kit.supervisor.report_approval_status(auto_yes=True, paused=False, input_control=True)
    assert session.approval_status == expected[condition]
    assert kit.sent == []


@pytest.mark.e2e
@pytest.mark.parametrize("case", ["unsupported", "conflict"])
def test_real_dashboard_explains_unsupported_permission(tmp_path: Path, case: str) -> None:
    dashboard = Dashboard(tmp_path, case, driver=Path(__file__).with_name("pty_approval_status.py"))
    expected = (
        "unsupported-permission-layout"
        if case == "unsupported"
        else "conflicting-permission-context"
    )
    try:
        dashboard.read_until(lambda text: "APPROVAL_PENDING" in text)
        dashboard.press("d")
        dashboard.read_until(lambda text: expected in text)
        dashboard.read_until(lambda text: "stay with same model" in text)
    finally:
        assert dashboard.quit() == 0


@pytest.mark.parametrize("state", [ActionState.PLANNED, ActionState.SENT])
def test_persisted_inflight_action_is_visible_without_a_verification_deadline(
    tmp_path: Path, state: ActionState
) -> None:
    kit, session = _kit(tmp_path)
    record = kit.supervisor.store.plan(
        "pending", provider="claude", session=session.ref.key(), process=session.describe_process()
    )
    kit.supervisor.store.mark(record.key, state)
    session.pending_key = record.key
    session.verify_after = None  # A clock jump invalidates schedules, not durable intent.
    kit.supervisor.report_approval_status(auto_yes=True, paused=False, input_control=True)
    assert session.approval_status == "action-in-flight"
    assert kit.supervisor.approve_pending()[session.ref.key()] == "action-in-flight"
    assert kit.sent == []
