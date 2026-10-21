# SPDX-FileCopyrightText: 2026 Marcel Petrick
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""This-run counts are outcomes, not inferred work or historical totals."""

from pathlib import Path

import pytest

from agent_while_true.activity import RunActivity
from agent_while_true.config import Mode
from agent_while_true.ui import render_status
from tests import harness, screens
from tests.pty_dashboard import Dashboard


def _kit(tmp_path, screen, mode=Mode.AUTO):
    kit = harness.build(tmp_path, mode=mode)
    info = kit.inspector.add_claude(15102)
    ref = kit.terminal.add("/Sessions/1", shell_pid=100, foreground_pid=15102, screen=list(screen))
    kit.supervisor.select(ref, info.identity, "claude", "synthetic activity")
    return kit, ref.key()


def test_permission_resend_is_not_another_unblocked_permission(tmp_path: Path) -> None:
    kit, key = _kit(tmp_path, screens.CLAUDE_APPROVAL_YES_NO)
    kit.supervisor.tick()
    assert kit.supervisor.approve_pending()[key] == "approved"
    assert kit.supervisor.activity.approvals == 1
    kit.clock.advance(3)
    assert kit.supervisor.approve_pending()[key] == "resent"
    assert kit.supervisor.activity.approvals == 1
    assert kit.supervisor.activity.approval_resends == 1
    kit.clock.advance(3)
    kit.supervisor.approve_pending()
    assert kit.supervisor.activity.approvals == 1
    assert kit.supervisor.activity.budget_restarts == 0


@pytest.mark.parametrize("own_action", [True, False])
def test_only_own_verified_resume_counts(tmp_path: Path, own_action: bool) -> None:
    kit, key = _kit(tmp_path, screens.CLAUDE_SESSION_LIMIT)
    kit.supervisor.tick()
    kit.clock.advance(36000)
    harness.refresh_quota(kit)
    kit.terminal.set_screen("/Sessions/1", list(screens.CLAUDE_READY_TO_RESUME))
    assert kit.supervisor.tick()[0].allowed
    assert kit.supervisor.activity.resume_attempts == 1
    assert kit.supervisor.activity.budget_restarts == 0
    if not own_action:
        kit.supervisor.sessions[key].run_action_key = ""
    kit.terminal.set_screen("/Sessions/1", list(screens.CLAUDE_ACTIVE))
    kit.clock.advance(5)
    harness.refresh_quota(kit)
    assert kit.supervisor.tick()[0].reason == "resume-verified"
    assert kit.supervisor.activity.budget_restarts == int(own_action)
    kit.supervisor.tick()
    assert kit.supervisor.activity.budget_restarts == int(own_action)
    assert harness.build(tmp_path).supervisor.activity == RunActivity()


def test_arming_wait_does_not_claim_work_restarted(tmp_path: Path) -> None:
    kit, _ = _kit(tmp_path, screens.CLAUDE_LIMIT_MENU_SHORTLY)
    assert kit.supervisor.tick()[0].allowed
    kit.terminal.set_screen("/Sessions/1", list(screens.CLAUDE_SELF_HEALING))
    kit.clock.advance(5)
    harness.refresh_quota(kit)
    kit.supervisor.tick()
    assert kit.supervisor.activity.waits_armed == 1
    assert kit.supervisor.activity.budget_restarts == 0


def test_observer_never_claims_approvals(tmp_path: Path) -> None:
    kit, _ = _kit(tmp_path, screens.CLAUDE_APPROVAL_YES_NO, Mode.OBSERVE)
    kit.supervisor.tick()
    assert kit.supervisor.approve_pending() == {}
    assert kit.supervisor.activity == RunActivity()


def test_total_counts_only_initial_answers_and_verified_recoveries() -> None:
    activity = RunActivity(
        approvals=7,
        approval_resends=4,
        resume_attempts=20,
        budget_restarts=2,
        capacity_recoveries=3,
        waits_armed=9,
    )
    assert activity.unblock_actions == 12
    assert "Unblock actions: 12" in activity.line()
    assert "Budget restarts: 2 verified" in activity.line()
    assert "Capacity recoveries: 3 verified" in activity.line()
    assert RunActivity().unblock_actions == 0


@pytest.mark.parametrize("width", [40, 80, 120, 180])
def test_counter_is_visible_when_scrolling(width: int) -> None:
    from datetime import UTC, datetime

    from agent_while_true.config import Config

    activity = RunActivity(approvals=7, budget_restarts=2, capacity_recoveries=3, waits_armed=1)
    frame = render_status(
        [],
        now=datetime.now(UTC),
        config=Config(),
        width=width,
        height=8,
        scroll_offset=9999,
        show_help=True,
        activity=activity,
    )
    assert ("unblocks:12" if width < 160 else "Unblock actions: 12") in frame
    assert ("approvals:7" if width < 160 else "Approvals sent: 7") in frame
    assert ("budget:2" if width < 160 else "Budget restarts: 2") in frame
    assert ("capacity:3" if width < 160 else "Capacity recoveries: 3") in frame
    assert ("waits:1" if width < 160 else "Waits armed: 1") in frame
    assert "[A]" in frame
    assert "[y]" in frame


@pytest.mark.parametrize("mode", [Mode.OBSERVE, Mode.ASK, Mode.AUTO])
@pytest.mark.parametrize("auto_yes", [False, True])
def test_narrow_controls_remain_visible(mode, auto_yes) -> None:
    from agent_while_true.config import Config
    from agent_while_true.ui import compact_toggles

    text = compact_toggles(Config(mode=mode), auto_yes=auto_yes)
    assert len(text) <= 36
    assert "[A]" in text
    assert "[y]" in text
    if auto_yes and mode is not Mode.AUTO:
        assert "ON/inert" in text
    assert ("cap:ON" if mode is Mode.AUTO else "cap:ON/inert") in text


@pytest.mark.parametrize("mode", [Mode.OBSERVE, Mode.ASK, Mode.AUTO])
@pytest.mark.parametrize("enabled", [False, True])
def test_capacity_policy_status_is_visible_without_granting_permission(mode, enabled) -> None:
    from dataclasses import replace
    from datetime import UTC, datetime

    from agent_while_true.config import Config

    config = Config(mode=mode)
    config = replace(config, policy=replace(config.policy, allow_codex_capacity_retry=enabled))
    frame = render_status([], now=datetime.now(UTC), config=config, width=180)
    expected = "OFF" if not enabled else "ON" if mode is Mode.AUTO else "ON/inert"
    assert f"capacity retry: {expected}" in frame


@pytest.mark.parametrize(("paused", "input_control"), [(True, True), (False, False)])
@pytest.mark.parametrize("width", [40, 80, 120, 180])
def test_capacity_policy_is_inert_while_paused_or_without_input_control(
    paused: bool, input_control: bool, width: int
) -> None:
    from datetime import UTC, datetime

    from agent_while_true.config import Config

    frame = render_status(
        [],
        now=datetime.now(UTC),
        config=Config(mode=Mode.AUTO),
        width=width,
        paused=paused,
        input_control=input_control,
    )
    assert ("cap:ON/inert" if width < 120 else "capacity retry: ON/inert") in frame
    if paused:
        assert "PAUSED" in frame.splitlines()[1]


def test_capacity_details_explain_same_model_and_fresh_quota(tmp_path: Path) -> None:
    from agent_while_true.ui import session_details

    kit, key = _kit(tmp_path, screens.CLAUDE_ACTIVE)
    details = "\n".join(
        session_details(
            kit.supervisor.sessions[key], kit.clock.wall, 2, capacity_retry_status="ON/inert"
        )
    )
    assert "Capacity retry: ON/inert" in details
    assert "fresh available quota, same model and bounded attempts required" in details


@pytest.mark.e2e
def test_real_pty_shows_this_run_counts_without_input(tmp_path: Path) -> None:
    dashboard = Dashboard(tmp_path, "--no-color")
    try:
        dashboard.read_until(
            lambda text: "unblocks:0" in text and "budget:0" in text and "capacity:0" in text
        )
    finally:
        assert dashboard.quit() == 0


@pytest.mark.e2e
def test_real_pty_shows_earned_count_and_readable_history(tmp_path: Path) -> None:
    dashboard = Dashboard(tmp_path, driver=Path(__file__).with_name("pty_run_activity.py"))
    try:
        dashboard.read_until(
            lambda text: "unblocks:2" in text and "approvals:1" in text and "capacity:1" in text
        )
        start = len(dashboard.text)
        dashboard.press("G")
        dashboard.read_until(lambda text: "Same-model capacity recovery verified" in text[start:])
        assert "unblocks:2" in dashboard.text[start:]
        assert "capacity:1" in dashboard.text[start:]
    finally:
        assert dashboard.quit() == 0
