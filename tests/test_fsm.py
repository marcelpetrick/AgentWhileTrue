# SPDX-FileCopyrightText: 2026 Marcel Petrick
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""End-to-end tests of the supervisor loop, driven entirely by fakes."""

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from pathlib import Path

import pytest

from agent_while_true.config import Config, Mode, Policy
from agent_while_true.quota import Availability, QuotaSnapshot, QuotaWindow
from agent_while_true.states import ActionState, SessionState
from tests import harness as harness_module
from tests import screens

SESSION = "/Sessions/1"
PID = 15102


def _claude_session(
    tmp_path: Path, *, mode=Mode.AUTO, screen=None, confirm=None, config=None, primed=True
):
    """Select a Claude session; the default ready screen follows an observed limit.

    ``primed`` shows the session limit for one tick first, the way the prompt
    arises in practice: the reset affordance authorises nothing on a process
    the supervisor never saw blocked.
    """
    kit = harness_module.build(tmp_path, mode=mode, confirm=confirm, config=config)
    info = kit.inspector.add_claude(PID)
    ready = screen is None
    ref = kit.terminal.add(
        SESSION,
        shell_pid=100,
        foreground_pid=PID,
        screen=list(
            screens.CLAUDE_SESSION_LIMIT
            if ready and primed
            else screen or screens.CLAUDE_READY_TO_RESUME
        ),
        title="project : claude",
    )
    kit.supervisor.select(ref, info.identity, "claude", "project : claude")
    if ready and primed:
        kit.supervisor.tick()
        assert kit.sent == []
        session = kit.supervisor.sessions[ref.key()]
        session.next_check_at = None
        kit.terminal.set_screen(SESSION, list(screens.CLAUDE_READY_TO_RESUME))
    return kit, ref


def test_a_ready_prompt_is_resumed_with_a_single_enter(tmp_path: Path) -> None:
    kit, _ = _claude_session(tmp_path)
    decisions = kit.supervisor.tick()
    assert decisions[0].allowed
    assert kit.sent == [(SESSION, "\r")]


def test_a_ready_prompt_never_preceded_by_a_limit_is_not_pressed(tmp_path: Path) -> None:
    """F0 layer 2: the 2026-09-18 live false positive, end to end.

    The supervised process shows the reset affordance with fresh AVAILABLE
    quota, but the supervisor never saw it blocked. Nothing may be typed.
    """
    kit, _ = _claude_session(tmp_path, primed=False)
    kit.quota["claude"].availability = Availability.AVAILABLE

    decisions = kit.supervisor.tick()
    assert not decisions[0].allowed
    assert decisions[0].reason == "ready-without-preceding-limit"
    assert kit.sent == []


def test_a_verified_resume_spends_the_limit_sighting(tmp_path: Path) -> None:
    # After the resume is verified, a later affordance on screen - an agent
    # quoting it, say - needs a fresh limit before it can authorise anything.
    kit, _ = _claude_session(tmp_path)
    kit.supervisor.tick()
    assert kit.sent == [(SESSION, "\r")]

    kit.terminal.set_screen(SESSION, list(screens.CLAUDE_ACTIVE))
    kit.clock.advance(10)
    harness_module.refresh_quota(kit)
    assert kit.supervisor.tick()[0].reason == "resume-verified"

    kit.terminal.set_screen(SESSION, [*screens.CLAUDE_READY_TO_RESUME, "  later"])
    kit.clock.advance(10)
    harness_module.refresh_quota(kit)
    assert kit.supervisor.tick()[0].reason == "ready-without-preceding-limit"
    assert len(kit.sent) == 1


def test_claude_limit_menu_arms_provider_auto_wait_and_verifies(tmp_path: Path) -> None:
    kit, _ = _claude_session(tmp_path, screen=list(screens.CLAUDE_LIMIT_MENU))
    kit.quota["claude"].availability = Availability.EXHAUSTED

    decisions = kit.supervisor.tick()
    assert decisions[0].allowed
    assert kit.sent == [(SESSION, "\x1b[B\r")]

    kit.terminal.set_screen(SESSION, list(screens.CLAUDE_SELF_HEALING))
    kit.clock.advance(5)
    harness_module.refresh_quota(kit)
    verified = kit.supervisor.tick()
    assert verified[0].reason == "verify:armed-provider-wait"
    session = kit.supervisor.sessions[kit.terminal.ref(SESSION).key()]
    assert session.state is SessionState.WAITING_FOR_RESET


def test_the_2026_09_20_deadlock_arms_and_verifies_end_to_end(tmp_path: Path) -> None:
    """The whole live failure, start to finish.

    Three Claude sessions held the wait menu through their 6:50pm reset because
    arming demanded an EXHAUSTED gauge, and Claude's status line reports at most
    99 %. The banner above the menu is the evidence; the wait Claude then
    announces without naming a time is what verifies the keystrokes landed.
    """
    kit, _ = _claude_session(tmp_path, screen=list(screens.CLAUDE_LIMIT_MENU_SHORTLY))
    kit.quota["claude"].availability = Availability.AVAILABLE
    kit.quota["claude"].windows = (QuotaWindow("session", 99.0, None),)

    decisions = kit.supervisor.tick()
    assert decisions[0].allowed, decisions[0].reason
    assert kit.sent == [(SESSION, "\x1b[B\r")]

    kit.terminal.set_screen(SESSION, list(screens.CLAUDE_CONTINUING_SHORTLY))
    kit.clock.advance(5)
    harness_module.refresh_quota(kit)
    verified = kit.supervisor.tick()
    assert verified[0].reason == "verify:armed-provider-wait"
    session = kit.supervisor.sessions[kit.terminal.ref(SESSION).key()]
    assert session.state is SessionState.WAITING_FOR_RESET


def test_a_stale_gauge_does_not_stop_the_banner_from_arming(tmp_path: Path) -> None:
    # A session parked on the menu stops refreshing its status line, so the
    # sample rots exactly when it is needed. The banner does not rot.
    kit, _ = _claude_session(tmp_path, screen=list(screens.CLAUDE_LIMIT_MENU_SHORTLY))
    kit.quota["claude"].availability = Availability.AVAILABLE
    kit.quota["claude"].observed_at = kit.clock.wall - timedelta(hours=1)

    decisions = kit.supervisor.tick()
    assert decisions[0].allowed, decisions[0].reason
    assert kit.sent == [(SESSION, "\x1b[B\r")]


def test_an_already_armed_wait_is_never_typed_into(tmp_path: Path) -> None:
    # The screen Claude shows once it is waiting by itself carries no action and
    # a stand-down veto, in the 2.1.278 wording that named no time.
    kit, _ = _claude_session(tmp_path, screen=list(screens.CLAUDE_CONTINUING_SHORTLY))
    kit.quota["claude"].availability = Availability.EXHAUSTED

    decisions = kit.supervisor.tick()
    assert not decisions[0].allowed
    assert decisions[0].reason == "provider-resumes-itself:claude/self-healing-soon"
    assert kit.sent == []


def test_claude_timed_auto_wait_banner_verifies_the_menu_action(tmp_path: Path) -> None:
    kit, _ = _claude_session(tmp_path, screen=list(screens.CLAUDE_LIMIT_MENU))
    kit.quota["claude"].availability = Availability.EXHAUSTED

    assert kit.supervisor.tick()[0].allowed
    pending_key = next(iter(kit.supervisor.sessions.values())).pending_key
    kit.terminal.set_screen(
        SESSION,
        ["Claude Code will continue automatically at 3:20am. Keep this session open."],
    )
    kit.clock.advance(5)
    harness_module.refresh_quota(kit)

    verified = kit.supervisor.tick()
    assert verified[0].reason == "verify:armed-provider-wait"
    assert kit.supervisor.store.records[pending_key].state is ActionState.VERIFIED


def test_an_outstanding_action_is_not_repeated_while_it_is_unverified(tmp_path: Path) -> None:
    # DANGER 17: one logical prompt has one action outstanding at a time,
    # however many times the same screen is scanned.
    kit, _ = _claude_session(tmp_path)
    kit.supervisor.tick()
    for _ in range(5):
        kit.clock.advance(1)  # still inside the verification window
        kit.supervisor.tick()
    assert kit.sent == [(SESSION, "\r")]


def test_a_verified_resume_is_never_re_sent(tmp_path: Path) -> None:
    kit, _ = _claude_session(tmp_path)
    kit.supervisor.tick()
    kit.terminal.set_screen(SESSION, list(screens.CLAUDE_ACTIVE))
    for _ in range(5):
        kit.clock.advance(10)
        harness_module.refresh_quota(kit)
        kit.supervisor.tick()
    assert kit.sent == [(SESSION, "\r")]


def test_observe_mode_never_sends_anything(tmp_path: Path) -> None:
    kit, _ = _claude_session(tmp_path, mode=Mode.OBSERVE)
    decisions = kit.supervisor.tick()
    assert not decisions[0].allowed
    assert decisions[0].reason == "observe-mode"
    # Observe mode still worked out what it would have done.
    assert decisions[0].action is not None
    assert kit.sent == []
    session = next(iter(kit.supervisor.sessions.values()))
    assert session.last_reason == decisions[0].reason
    assert session.observed_at == kit.clock.now()
    assert session.matched_ids


def test_ask_mode_sends_only_after_confirmation(tmp_path: Path) -> None:
    declined, _ = _claude_session(tmp_path / "no", mode=Mode.ASK, confirm=False)
    declined.supervisor.tick()
    assert declined.sent == []

    accepted, _ = _claude_session(tmp_path / "yes", mode=Mode.ASK, confirm=True)
    accepted.supervisor.tick()
    assert accepted.sent == [(SESSION, "\r")]


def test_refusals_count_episodes_not_repeated_polls(tmp_path: Path) -> None:
    kit, _ = _claude_session(tmp_path, mode=Mode.OBSERVE)
    for _ in range(3):
        kit.supervisor.tick()
        kit.clock.advance(2)
    log = (tmp_path / "agent-while-true.log").read_text()
    assert log.count("event=resume_refused provider=claude reason=observe-mode") == 1
    assert kit.sent == []


def test_ask_mode_without_a_way_to_ask_refuses(tmp_path: Path) -> None:
    kit, _ = _claude_session(tmp_path, mode=Mode.ASK, confirm=None)
    kit.supervisor.tick()
    assert kit.sent == []


def test_the_agent_exiting_between_deciding_and_typing_cancels_the_send(tmp_path: Path) -> None:
    # DANGER 2: codex/claude exits, zsh takes the foreground, the timer fires.
    # The swap happens after the first screen read, i.e. after the decision was
    # made but before the revalidation that guards the keystroke.
    kit, _ = _claude_session(tmp_path)
    reads = {"n": 0}

    def swap_after_first_read(session_id: str) -> None:
        reads["n"] += 1
        if reads["n"] == 1:
            shell = kit.inspector.add_shell(PID + 1)
            kit.terminal.set_foreground(session_id, shell.identity.pid)
            kit.terminal.set_screen(session_id, ["user@host ~/project %"])

    kit.terminal.after_read = swap_after_first_read
    decisions = kit.supervisor.tick()
    assert not decisions[0].allowed
    assert decisions[0].reason.startswith("revalidation-failed")
    assert kit.sent == []


def test_a_recycled_pid_is_not_the_same_process(tmp_path: Path) -> None:
    # DANGER 1: same PID, different start time.
    kit, _ = _claude_session(tmp_path)
    kit.inspector.add_claude(PID, start_time=999999)
    decisions = kit.supervisor.tick()
    assert decisions[0].reason == "process-identity-changed"
    assert kit.sent == []


def test_a_closed_tab_produces_no_input(tmp_path: Path) -> None:
    kit, _ = _claude_session(tmp_path)
    kit.terminal.close(SESSION)
    decisions = kit.supervisor.tick()
    assert not decisions[0].allowed
    assert kit.sent == []


def test_one_broken_session_does_not_stop_the_others(tmp_path: Path) -> None:
    kit, _ = _claude_session(tmp_path)
    other_info = kit.inspector.add_claude(20000, start_time=444, tty="pts/9")
    other_ref = kit.terminal.add(
        "/Sessions/2",
        shell_pid=200,
        foreground_pid=20000,
        screen=list(screens.CLAUDE_READY_TO_RESUME),
    )
    kit.supervisor.select(other_ref, other_info.identity, "claude", "other")
    kit.supervisor.sessions[other_ref.key()].limit_seen = True
    kit.terminal.close(SESSION)

    kit.supervisor.tick()
    assert kit.sent == [("/Sessions/2", "\r")]


def test_verification_settles_a_successful_resume(tmp_path: Path) -> None:
    kit, _ = _claude_session(tmp_path)
    kit.supervisor.tick()
    key = kit.supervisor.sessions[kit.terminal.ref(SESSION).key()].pending_key

    kit.terminal.set_screen(SESSION, list(screens.CLAUDE_ACTIVE))
    kit.clock.advance(10)
    harness_module.refresh_quota(kit)
    decisions = kit.supervisor.tick()

    assert decisions[0].reason == "resume-verified"
    assert kit.supervisor.store.records[key].state is ActionState.VERIFIED


def test_a_failed_resume_backs_off_instead_of_hammering(tmp_path: Path) -> None:
    kit, _ = _claude_session(tmp_path)
    kit.supervisor.tick()
    assert len(kit.sent) == 1

    # The prompt is still there after the keystroke.
    kit.clock.advance(10)
    harness_module.refresh_quota(kit)
    decisions = kit.supervisor.tick()
    assert decisions[0].reason == "verify:still-blocked"
    assert decisions[0].retry_at is not None

    # And the next tick respects the back-off rather than resending.
    kit.clock.advance(1)
    kit.supervisor.tick()
    assert len(kit.sent) == 1


def test_a_changing_screen_cannot_mint_an_unlimited_attempt_budget(tmp_path: Path) -> None:
    # The store counts attempts per prompt fingerprint, so a screen that keeps
    # changing would otherwise get a fresh budget on every tick. The
    # per-session counter is what actually bounds this.
    kit, _ = _claude_session(tmp_path)
    session = kit.supervisor.sessions[kit.terminal.ref(SESSION).key()]
    for round_number in range(8):
        kit.supervisor.tick()
        kit.clock.advance(120)
        harness_module.refresh_quota(kit)
        kit.terminal.set_screen(
            SESSION, [*screens.CLAUDE_READY_TO_RESUME, f"  build step {round_number}"]
        )
        session.verify_after = None
        session.next_check_at = None
    assert len(kit.sent) <= Config().max_resume_attempts


def test_a_suspend_across_the_reset_does_not_replay_a_stale_action(tmp_path: Path) -> None:
    # DANGER 9: reset at 02:00, sleep at 01:30, wake at 08:00.
    kit, _ = _claude_session(tmp_path, screen=list(screens.CLAUDE_SESSION_LIMIT))
    kit.supervisor.tick()
    assert kit.sent == []

    kit.clock.suspend(6 * 3600)
    harness_module.refresh_quota(kit)
    # On waking, the agent is gone and a shell has the foreground.
    shell = kit.inspector.add_shell(PID + 5)
    kit.terminal.set_foreground(SESSION, shell.identity.pid)
    kit.terminal.set_screen(SESSION, ["user@host ~/project %"])

    kit.supervisor.tick()
    assert kit.sent == []


def test_a_time_jump_discards_pending_schedules(tmp_path: Path) -> None:
    kit, _ = _claude_session(tmp_path, screen=list(screens.CLAUDE_SESSION_LIMIT))
    kit.supervisor.tick()
    session = kit.supervisor.sessions[kit.terminal.ref(SESSION).key()]
    session.next_check_at = kit.clock.wall
    kit.clock.suspend(3600)
    kit.supervisor.tick()
    assert session.next_check_at is None or session.next_check_at != kit.clock.wall


def test_a_wedged_terminal_marks_the_action_failed(tmp_path: Path) -> None:
    kit, _ = _claude_session(tmp_path)
    kit.terminal.send_fails = True
    decisions = kit.supervisor.tick()
    assert decisions[0].reason == "send-failed"
    session = kit.supervisor.sessions[kit.terminal.ref(SESSION).key()]
    assert kit.supervisor.store.records[session.pending_key].state is ActionState.FAILED


def test_codex_is_not_resumed_without_the_opt_in(tmp_path: Path) -> None:
    kit = harness_module.build(tmp_path, mode=Mode.AUTO)
    info = kit.inspector.add_codex(30000)
    ref = kit.terminal.add(
        "/Sessions/7",
        shell_pid=300,
        foreground_pid=30000,
        screen=list(screens.CODEX_USAGE_LIMIT),
    )
    kit.supervisor.select(ref, info.identity, "codex", "codex")
    decisions = kit.supervisor.tick()
    assert decisions[0].reason == "action-requires-policy:allow_codex_auto_resume"
    assert kit.sent == []


def test_codex_is_resumed_once_the_user_opts_in(tmp_path: Path) -> None:
    config = Config(mode=Mode.AUTO, policy=Policy(allow_codex_auto_resume=True))
    kit = harness_module.build(tmp_path, config=config)
    info = kit.inspector.add_codex(30000)
    ref = kit.terminal.add(
        "/Sessions/7",
        shell_pid=300,
        foreground_pid=30000,
        screen=list(screens.CODEX_USAGE_LIMIT),
    )
    kit.supervisor.select(ref, info.identity, "codex", "codex")
    kit.supervisor.tick()
    assert kit.sent == []
    due = kit.supervisor.sessions[ref.key()].next_check_at
    kit.clock.advance((due - kit.clock.wall).total_seconds())
    kit.supervisor.tick()
    assert kit.sent == [("/Sessions/7", "\x1b[200~continue\x1b[201~\r")]


def test_tick_warms_same_account_quota_before_the_first_decision(tmp_path: Path) -> None:
    config = Config(mode=Mode.AUTO, policy=Policy(allow_codex_auto_resume=True))
    kit = harness_module.build(tmp_path, config=config)
    blocked_pid, fresh_pid = 30000, 30001
    blocked_info = kit.inspector.add_codex(blocked_pid)
    fresh_info = kit.inspector.add_codex(fresh_pid, start_time=333, tty="pts/6")
    blocked_ref = kit.terminal.add(
        "/Sessions/7",
        shell_pid=300,
        foreground_pid=blocked_pid,
        screen=list(screens.CODEX_USAGE_LIMIT_WITH_PURCHASE_LINKS),
    )
    fresh_ref = kit.terminal.add(
        "/Sessions/8",
        shell_pid=301,
        foreground_pid=fresh_pid,
        screen=list(screens.CODEX_ACTIVE),
    )

    class SameAccountQuota:
        def __init__(self) -> None:
            self.freshest: QuotaSnapshot | None = None

        def snapshot(self, *, pid=None):
            observed_at = kit.clock.wall
            if pid == blocked_pid:
                observed_at -= timedelta(hours=1)
            current = QuotaSnapshot(
                provider="codex",
                availability=Availability.AVAILABLE,
                source="same-account",
                observed_at=observed_at,
            )
            if self.freshest is None or observed_at > self.freshest.observed_at:
                self.freshest = current
            return self.freshest

    kit.supervisor.quota_sources["codex"] = SameAccountQuota()
    kit.supervisor.select(blocked_ref, blocked_info.identity, "codex", "blocked")
    kit.supervisor.select(fresh_ref, fresh_info.identity, "codex", "fresh")

    decisions = kit.supervisor.tick()

    assert not decisions[0].allowed  # Fresh pre-limit quota cannot bypass reset.
    due = kit.supervisor.sessions[blocked_ref.key()].next_check_at
    kit.clock.advance((due - kit.clock.wall).total_seconds())
    decisions = kit.supervisor.tick()
    assert decisions[0].allowed
    assert kit.sent == [("/Sessions/7", "\x1b[200~continue\x1b[201~\r")]


def test_prune_removes_a_selection_whose_tab_is_gone(tmp_path: Path) -> None:
    # DANGER 20: a selection must not survive its tab and transfer to a new one.
    kit, _ = _claude_session(tmp_path)
    kit.terminal.close(SESSION)
    kit.supervisor.prune_and_rebind()
    assert kit.supervisor.sessions == {}


def test_marking_a_session_unsafe_stops_it(tmp_path: Path) -> None:
    kit, ref = _claude_session(tmp_path)
    kit.supervisor.mark_unsafe(ref.key(), "manual")
    decisions = kit.supervisor.tick()
    assert decisions[0].reason == "session-marked-unsafe"
    assert kit.sent == []
    assert kit.supervisor.sessions[ref.key()].state is SessionState.UNSAFE


@pytest.mark.parametrize("screen_name", ["CLAUDE_SELF_HEALING", "CLAUDE_SPEND_LIMIT"])
def test_vetoed_screens_are_never_actioned(tmp_path: Path, screen_name: str) -> None:
    kit, _ = _claude_session(tmp_path, screen=list(getattr(screens, screen_name)))
    kit.supervisor.tick()
    assert kit.sent == []


def test_the_event_log_records_the_send_without_the_screen(tmp_path: Path) -> None:
    kit, _ = _claude_session(tmp_path)
    kit.supervisor.tick()
    written = (tmp_path / "agent-while-true.log").read_text()
    assert "event=resume_sent" in written
    assert "press enter to continue" not in written
    assert "session limit" not in written


def _session_state(kit):
    return kit.supervisor.sessions[kit.terminal.ref(SESSION).key()].state


def test_a_shell_in_the_foreground_does_not_keep_the_agent_state(tmp_path: Path) -> None:
    """F3, live 2026-09-18 14:30: the tab held a shell while the row read ACTIVE."""
    kit, _ = _claude_session(tmp_path, screen=list(screens.CLAUDE_ACTIVE))
    kit.supervisor.tick()
    assert _session_state(kit) is SessionState.ACTIVE

    shell = kit.inspector.add_shell(PID + 1)
    kit.terminal.set_foreground(SESSION, shell.identity.pid)
    kit.clock.advance(2)
    decisions = kit.supervisor.tick()
    assert decisions[0].reason == "not-automatable:idle-shell"
    assert _session_state(kit) is SessionState.UNKNOWN
    assert kit.sent == []


@pytest.mark.parametrize(
    ("hook", "value"),
    [
        ("environ", "TMUX"),
        ("environ", "STY"),
        ("environ", "SSH_CONNECTION"),
        ("_detect_container", "container-cgroup"),
        ("_ancestor_blocker", "remote-ancestor=ssh"),
        ("_ancestor_blocker", "nested-terminal-ancestor=screen"),
    ],
)
def test_every_unsupported_environment_reads_unsupported(
    tmp_path: Path, monkeypatch, hook: str, value: str
) -> None:
    # The old mapping matched four literal blocker strings and missed, e.g.,
    # tmux-environment-marker, screen, and every ancestor other than tmux.
    from agent_while_true import classify as classify_module

    kit, _ = _claude_session(tmp_path, screen=list(screens.CLAUDE_ACTIVE))
    kit.supervisor.tick()
    if hook == "environ":
        info = kit.inspector.processes[PID]
        kit.inspector.processes[PID] = replace(info, environ_keys=info.environ_keys | {value})
    else:
        monkeypatch.setattr(classify_module, hook, lambda info: value)
    kit.clock.advance(2)
    kit.supervisor.tick()
    assert _session_state(kit) is SessionState.UNSUPPORTED
    assert kit.sent == []
