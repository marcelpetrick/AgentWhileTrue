# SPDX-FileCopyrightText: 2026 Marcel Petrick
# SPDX-License-Identifier: GPL-3.0-or-later
"""Regressions for the September 10 live Codex retry investigation."""

from dataclasses import replace
from datetime import datetime, timedelta
from itertools import pairwise
from zoneinfo import ZoneInfo

import pytest

from agent_watch.config import Config, Mode, Policy
from agent_watch.quota import Availability, QuotaWindow
from agent_watch.state_store import StateStore
from agent_watch.states import SessionState
from tests.harness import build

# The observed banner wording is transcribed in debugging.md. The empty
# composer is the existing tested Codex shape, not a claimed full live capture.
COMPOSER = "\N{SINGLE RIGHT-POINTING ANGLE QUOTATION MARK} "
TONIGHTS_LIMIT = ["▌ You've hit your usage limit. Try again at 9:52 PM.", "", COMPOSER]
START = datetime(2026, 9, 10, 21, 50, 52, tzinfo=ZoneInfo("Europe/Berlin"))


def setup_codex(tmp_path, *, availability=Availability.UNKNOWN, config=None):
    kit = build(
        tmp_path,
        now=START,
        config=config or Config(mode=Mode.AUTO, policy=Policy(allow_codex_auto_resume=True)),
    )
    info = kit.inspector.add_codex(423301)
    ref = kit.terminal.add(
        "/Sessions/1", shell_pid=100, foreground_pid=info.pid, screen=TONIGHTS_LIMIT
    )
    kit.supervisor.select(ref, info.identity, "codex", "synthetic")
    kit.quota["codex"].availability = availability
    return kit, kit.supervisor.sessions[ref.key()]


def test_reset_does_not_move_to_tomorrow_and_retry_occurs(tmp_path):
    kit, session = setup_codex(tmp_path)
    kit.supervisor.tick()
    anchored = session.reset_at
    assert anchored == START.replace(hour=21, minute=52, second=0)
    kit.clock.advance(69)
    kit.supervisor.tick()
    assert session.reset_at == anchored
    assert len(kit.sent) == 1


def test_pre_limit_available_quota_cannot_send_before_printed_reset(tmp_path):
    kit, _ = setup_codex(tmp_path, availability=Availability.AVAILABLE)
    kit.supervisor.tick()
    assert kit.sent == []


def test_manual_recovery_is_observed_while_action_waits(tmp_path):
    kit, session = setup_codex(tmp_path)
    kit.supervisor.tick()
    kit.terminal.set_screen("/Sessions/1", ["• Working", "", COMPOSER])
    kit.clock.advance(2)
    kit.supervisor.tick()
    assert session.state is SessionState.ACTIVE
    assert kit.sent == []


def test_backoff_is_bounded_across_fingerprint_changes_and_reselection(tmp_path):
    kit, session = setup_codex(tmp_path)
    kit.supervisor.tick()
    reset = session.reset_at
    kit.clock.advance(69)
    sent_at = []
    for attempt, delay in enumerate(kit.supervisor.config.retry_schedule, 1):
        if attempt > 1:
            kit.clock.advance(delay)
        kit.supervisor.tick()
        sent_at.append(kit.clock.wall)
        assert len(kit.sent) == attempt
        kit.terminal.set_screen("/Sessions/1", [f"retry history {attempt}", *TONIGHTS_LIMIT])
        kit.clock.advance(1)
        kit.supervisor.tick()  # Verification completes before the next delay starts.
        if attempt == 4:
            kit.supervisor.store = StateStore.in_directory(tmp_path).load(now=kit.clock.wall)
            kit.supervisor.select(session.ref, session.identity, "codex", "synthetic")
            session = kit.supervisor.sessions[session.ref.key()]
    assert sent_at[0] == reset + timedelta(seconds=1)
    assert [int((right - left).total_seconds()) for left, right in pairwise(sent_at)] == [
        delay + 1 for delay in kit.supervisor.config.retry_schedule[1:]
    ]
    kit.clock.advance(86400)
    kit.supervisor.tick()
    assert len(kit.sent) == 11
    assert session.last_reason == "retry-budget-exhausted"
    log = (tmp_path / "agent-watch.log").read_text()
    assert log.count("event=resume_sent ") == 11
    assert log.count("event=resume_gave_up ") == 1
    assert "Try again" not in log


def test_late_start_uses_absolute_window_to_date_old_banner(tmp_path):
    kit, session = setup_codex(tmp_path, availability=Availability.AVAILABLE)
    reset = START.replace(hour=21, minute=52, second=0)
    kit.quota["codex"].windows = (QuotaWindow("session", 99, reset),)
    kit.clock.advance(3600)
    kit.supervisor.tick()
    assert session.reset_at == reset
    assert len(kit.sent) == 1


@pytest.mark.parametrize("mode", [Mode.ASK, Mode.OBSERVE])
def test_retry_episode_not_written_without_auto_lock_workflow(tmp_path, mode):
    kit, _ = setup_codex(
        tmp_path, config=Config(mode=mode, policy=Policy(allow_codex_auto_resume=True))
    )
    kit.supervisor.tick()
    kit.clock.advance(3600)
    kit.supervisor.tick()
    assert kit.sent == []
    assert not (tmp_path / "state.json").exists()


def test_fresh_later_weekly_exhaustion_vetoes_timed_retry(tmp_path):
    kit, session = setup_codex(tmp_path)
    kit.supervisor.tick()
    kit.clock.advance(69)
    kit.quota["codex"].availability = Availability.EXHAUSTED
    kit.quota["codex"].observed_at = kit.clock.wall
    kit.quota["codex"].windows = (QuotaWindow("weekly", 100, kit.clock.wall + timedelta(days=2)),)
    kit.supervisor.tick()
    assert kit.sent == []
    assert "other-limit-still-exhausted" in session.last_reason


def test_config_schedule_must_be_finite_positive_and_bounded():
    for schedule in ((), (0,), (float("inf"),), (1,) * 33):
        with pytest.raises(ValueError, match="RETRY_SCHEDULE"):
            replace(Config(), retry_schedule=schedule)


def test_pre_reset_exhaustion_can_be_trialed_but_post_reset_exhaustion_vetoes(tmp_path):
    kit, session = setup_codex(tmp_path, availability=Availability.EXHAUSTED)
    reset = START.replace(hour=21, minute=52, second=0)
    kit.quota["codex"].windows = (QuotaWindow("session", 100, reset),)
    kit.supervisor.tick()
    assert kit.sent == []
    kit.clock.advance(69)
    assert kit.supervisor.tick()[0].allowed
    assert session.quota.availability is Availability.EXHAUSTED  # No fabricated availability.
    kit.clock.advance(1)
    kit.supervisor.tick()
    kit.quota["codex"].observed_at = kit.clock.wall
    kit.clock.advance(2)
    assert not kit.supervisor.tick()[0].allowed
    assert len(kit.sent) == 1


def test_near_retry_deadlines_wake_loop_without_past_deadline_busy_wait(tmp_path):
    from agent_watch.cli import _scan_delay

    kit, session = setup_codex(tmp_path)
    assert _scan_delay(kit.supervisor, 2) == 2
    session.next_check_at = kit.clock.wall + timedelta(seconds=1)
    assert _scan_delay(kit.supervisor, 2) == 1
    session.next_check_at = kit.clock.wall - timedelta(seconds=1)
    assert _scan_delay(kit.supervisor, 2) == 2


def test_config_schedule_parses_commas_and_summary_counts_retry_events(tmp_path):
    from agent_watch.config import load
    from agent_watch.summary import render_summary

    assert load(
        config_path=tmp_path / "missing", environ={"AGENT_WATCH_RETRY_SCHEDULE": "1,2,600"}
    ).retry_schedule == (1, 2, 600)
    events = tmp_path / "events.log"
    stamp = START.astimezone().strftime("%Y-%m-%d %H:%M:%S,000")
    events.write_text(
        f"{stamp} INFO event=resume_retry_scheduled session=s attempt=1/11\n"
        f"{stamp} INFO event=resume_gave_up session=s attempt=11/11\n"
    )
    report = render_summary(events, now=START, days=1)
    assert "scheduled=1 gave-up=1" in report


@pytest.mark.parametrize("tail", [["• Working", COMPOSER], [COMPOSER + "unfinished draft"]])
def test_old_limit_or_nonempty_draft_never_gets_continue(tmp_path, tail):
    kit, _ = setup_codex(tmp_path, availability=Availability.AVAILABLE)
    kit.supervisor.tick()
    kit.clock.advance(69)
    kit.terminal.set_screen("/Sessions/1", [*TONIGHTS_LIMIT[:-1], *tail])
    kit.supervisor.tick()
    assert kit.sent == []
