# SPDX-FileCopyrightText: 2026 Marcel Petrick
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Budget renewal contracts exercised without waiting for real provider usage."""

from datetime import timedelta
from pathlib import Path

import pytest

from agent_while_true.quota import Availability, QuotaWindow
from agent_while_true.states import ActionState
from tests import harness, screens

SESSION = "/Sessions/1"
PID = 15102


@pytest.mark.parametrize("last_scope", ["weekly", "opus", "sonnet"])
def test_claude_continues_only_after_every_exhausted_budget_renews(
    tmp_path: Path, last_scope: str
) -> None:
    kit = harness.build(tmp_path)
    identity = kit.inspector.add_claude(PID).identity
    ref = kit.terminal.add(
        SESSION,
        shell_pid=100,
        foreground_pid=PID,
        screen=list(screens.CLAUDE_SESSION_LIMIT),
    )
    kit.supervisor.select(ref, identity, "claude", "renewal contract")
    quota = kit.quota["claude"]
    short_reset = kit.clock.wall + timedelta(hours=5)
    last_reset = kit.clock.wall + timedelta(days=7)
    quota.availability = Availability.EXHAUSTED
    quota.windows = (
        QuotaWindow("session", 100.0, short_reset),
        QuotaWindow(last_scope, 100.0, last_reset),
    )
    kit.supervisor.tick()
    assert not kit.sent

    # The five-hour window is genuinely renewed, but the separate week/model
    # budget remains spent. Even Claude's ready affordance cannot override it.
    kit.clock.advance(5 * 3600 + 60)
    harness.refresh_quota(kit)
    quota.windows = (
        QuotaWindow("session", 0.0, kit.clock.wall + timedelta(hours=5)),
        QuotaWindow(last_scope, 100.0, last_reset),
    )
    kit.terminal.set_screen(SESSION, list(screens.CLAUDE_READY_TO_RESUME))
    decision = kit.supervisor.tick()[0]
    assert decision.reason == f"other-limit-still-exhausted:{last_scope}"
    assert not kit.sent

    # Passing the final reset and grace alone still does not replenish quota.
    kit.clock.advance((last_reset - kit.clock.wall).total_seconds() + 61)
    harness.refresh_quota(kit)
    assert not kit.supervisor.tick()[0].allowed
    assert not kit.sent

    # Fresh provider evidence now confirms every exhausted window renewed.
    # Keep exactly the same process and model; the only input is bare Enter.
    quota.availability = Availability.AVAILABLE
    quota.windows = (
        QuotaWindow("session", 1.0, kit.clock.wall + timedelta(hours=5)),
        QuotaWindow(last_scope, 0.0, kit.clock.wall + timedelta(days=7)),
    )
    harness.refresh_quota(kit)
    assert kit.supervisor.tick()[0].allowed
    assert kit.sent == [(SESSION, "\r")]
    pending = kit.supervisor.sessions[ref.key()].pending_key
    kit.terminal.set_screen(SESSION, list(screens.CLAUDE_ACTIVE))
    kit.clock.advance(5)
    harness.refresh_quota(kit)
    assert kit.supervisor.tick()[0].reason == "resume-verified"
    assert kit.supervisor.store.records[pending].state is ActionState.VERIFIED
    assert kit.sent == [(SESSION, "\r")]


@pytest.mark.parametrize("scope", ["session", "weekly", "opus", "sonnet"])
def test_already_armed_claude_wait_is_untouched_when_budget_returns(
    tmp_path: Path, scope: str
) -> None:
    kit = harness.build(tmp_path)
    identity = kit.inspector.add_claude(PID).identity
    ref = kit.terminal.add(
        SESSION,
        shell_pid=100,
        foreground_pid=PID,
        screen=list(screens.CLAUDE_SELF_HEALING),
    )
    kit.supervisor.select(ref, identity, "claude", "armed wait contract")
    quota = kit.quota["claude"]
    quota.availability = Availability.EXHAUSTED
    quota.windows = (QuotaWindow(scope, 100.0, kit.clock.wall + timedelta(seconds=30)),)
    assert not kit.supervisor.tick()[0].allowed

    kit.clock.advance(91)
    quota.availability = Availability.AVAILABLE
    quota.windows = (QuotaWindow(scope, 0.0, None),)
    harness.refresh_quota(kit)
    decision = kit.supervisor.tick()[0]
    assert not decision.allowed
    assert decision.reason.startswith("provider-resumes-itself:")
    assert not kit.sent
