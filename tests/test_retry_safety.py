# SPDX-FileCopyrightText: 2026 Marcel Petrick <mail@marcelpetrick.it>
# SPDX-License-Identifier: GPL-3.0-or-later
"""Safety boundaries for persistent, bounded Codex timed retries."""

from __future__ import annotations

from agent_watch.config import Config, Mode, Policy
from agent_watch.quota import Availability
from agent_watch.states import ActionState, SessionState
from tests.harness import build
from tests.test_codex_retry import COMPOSER, START, TONIGHTS_LIMIT, setup_codex


def _retry_config(*delays: float) -> Config:
    return Config(
        mode=Mode.AUTO,
        policy=Policy(allow_codex_auto_resume=True),
        retry_schedule=delays,
    )


def _advance_to_first_send(kit) -> None:
    kit.supervisor.tick()
    kit.clock.advance(69)
    assert kit.supervisor.tick()[0].allowed


def test_changed_screen_fingerprints_share_one_bounded_episode(tmp_path) -> None:
    kit, session = setup_codex(tmp_path, config=_retry_config(1, 2))
    _advance_to_first_send(kit)
    first_episode = session.retry_episode_key
    first_prompt_key = session.reset_prompt_key

    kit.terminal.set_screen(
        "/Sessions/1", [*TONIGHTS_LIMIT[:-1], "status changed after send", COMPOSER]
    )
    kit.clock.advance(1)
    assert kit.supervisor.tick()[0].reason == "verify:still-blocked"
    kit.clock.advance(2)
    assert kit.supervisor.tick()[0].allowed
    kit.clock.advance(1)
    assert kit.supervisor.tick()[0].reason == "verify:still-blocked"

    episode = kit.supervisor.store.get_episode(first_episode)
    assert episode is not None
    assert episode.prompt_key == first_prompt_key
    assert episode.attempts == 2
    assert episode.exhausted
    kit.clock.advance(600)
    assert not kit.supervisor.tick()[0].allowed
    assert len(kit.sent) == 2


def test_restart_verifies_sent_attempt_without_resending(tmp_path) -> None:
    config = _retry_config(1, 2)
    kit, session = setup_codex(tmp_path, config=config)
    _advance_to_first_send(kit)
    episode_key = session.retry_episode_key
    pending_key = session.pending_key
    assert kit.supervisor.store.records[pending_key].state is ActionState.SENT

    restarted = build(tmp_path, now=kit.clock.wall, config=config)
    info = restarted.inspector.add_codex(423301)
    ref = restarted.terminal.add(
        "/Sessions/1", shell_pid=100, foreground_pid=info.pid, screen=TONIGHTS_LIMIT
    )
    restarted.supervisor.select(ref, info.identity, "codex", "synthetic")
    decision = restarted.supervisor.tick()[0]

    assert decision.reason == "verify:still-blocked"
    assert restarted.sent == []
    episode = restarted.supervisor.store.get_episode(episode_key)
    assert episode is not None
    assert episode.attempts == 1
    assert episode.pending_key == ""


def test_restart_treats_planned_attempt_as_unsettled_and_never_resends(tmp_path) -> None:
    config = _retry_config(1, 2)
    kit, session = setup_codex(tmp_path, config=config)
    kit.supervisor.tick()
    episode = kit.supervisor.store.get_episode(session.retry_episode_key)
    assert episode is not None
    action_key = f"{episode.key}-1"
    kit.supervisor.store.reserve_episode_attempt(episode.key, action_key)
    kit.supervisor.store.plan(
        action_key,
        provider="codex",
        session=session.ref.key(),
        process=session.describe_process(),
    )

    restarted = build(tmp_path, now=START.replace(hour=22), config=config)
    info = restarted.inspector.add_codex(423301)
    ref = restarted.terminal.add(
        "/Sessions/1", shell_pid=100, foreground_pid=info.pid, screen=TONIGHTS_LIMIT
    )
    restarted.supervisor.select(ref, info.identity, "codex", "synthetic")
    for _ in range(3):
        assert restarted.supervisor.tick()[0].reason == "retry-attempt-unsettled"
        restarted.clock.advance(60)
    assert restarted.sent == []


def test_manual_recovery_completes_episode_before_due_retry(tmp_path) -> None:
    kit, session = setup_codex(tmp_path, config=_retry_config(1, 2))
    kit.supervisor.tick()
    key = session.retry_episode_key
    kit.terminal.set_screen("/Sessions/1", ["• Working", "", COMPOSER])
    kit.clock.advance(30)
    decision = kit.supervisor.tick()[0]
    episode = kit.supervisor.store.get_episode(key)
    assert decision.reason.startswith("no-recognised-blocking-prompt")
    assert session.state is SessionState.ACTIVE
    assert episode is not None
    assert episode.completed
    assert kit.sent == []


def test_fresh_exhausted_quota_blocks_due_timed_retry(tmp_path) -> None:
    kit, _ = setup_codex(
        tmp_path,
        availability=Availability.EXHAUSTED,
        config=_retry_config(1, 2),
    )
    kit.quota["codex"].observed_at = kit.clock.wall
    kit.supervisor.tick()
    kit.clock.advance(69)
    kit.quota["codex"].observed_at = kit.clock.wall
    decision = kit.supervisor.tick()[0]
    assert not decision.allowed
    assert decision.reason == "usage-not-confirmed-available"
    assert kit.sent == []


def test_invalid_retry_store_never_uses_time_only_authorization(tmp_path) -> None:
    (tmp_path / "state.json").write_text("{malformed")
    kit, _ = setup_codex(tmp_path, config=_retry_config(1, 2))
    kit.supervisor.tick()
    kit.clock.advance(69)
    decision = kit.supervisor.tick()[0]
    assert not decision.allowed
    assert decision.reason == "retry-state-unreadable"
    assert kit.sent == []


def test_identity_change_during_revalidation_cancels_send(tmp_path) -> None:
    kit, _ = setup_codex(tmp_path, config=_retry_config(1, 2))
    kit.supervisor.tick()
    kit.clock.advance(69)
    reads = 0

    def replace_foreground(_session_id: str) -> None:
        nonlocal reads
        reads += 1
        if reads == 2:
            shell = kit.inspector.add_shell(90000)
            kit.terminal.set_foreground("/Sessions/1", shell.pid)

    kit.terminal.after_read = replace_foreground
    decision = kit.supervisor.tick()[0]
    assert not decision.allowed
    assert decision.reason.startswith("revalidation-failed:")
    assert kit.sent == []


def test_prompt_change_during_revalidation_cancels_send(tmp_path) -> None:
    kit, _ = setup_codex(tmp_path, config=_retry_config(1, 2))
    kit.supervisor.tick()
    kit.clock.advance(69)
    reads = 0

    def change_prompt(_session_id: str) -> None:
        nonlocal reads
        reads += 1
        if reads == 2:
            kit.terminal.set_screen("/Sessions/1", ["• Working", "", COMPOSER])

    kit.terminal.after_read = change_prompt
    decision = kit.supervisor.tick()[0]
    assert not decision.allowed
    assert decision.reason.startswith("revalidation-failed:")
    assert kit.sent == []


def test_final_recheck_cancellation_does_not_consume_typed_attempt_budget(tmp_path) -> None:
    kit, session = setup_codex(tmp_path, config=_retry_config(1))
    kit.supervisor.tick()
    kit.clock.advance(69)
    reads = 0

    def become_active_before_final_recheck(_session_id: str) -> None:
        nonlocal reads
        reads += 1
        if reads == 2:
            kit.terminal.set_screen("/Sessions/1", ["• Working", "", COMPOSER])

    kit.terminal.after_read = become_active_before_final_recheck
    decision = kit.supervisor.tick()[0]
    episode = kit.supervisor.store.get_episode(session.retry_episode_key)

    assert decision.reason.startswith("revalidation-failed:")
    assert kit.sent == []
    assert episode is not None
    assert episode.attempts == 0
    assert not episode.exhausted
    assert episode.pending_key == ""
    assert next(iter(kit.supervisor.store.records.values())).state is ActionState.FAILED

    kit.terminal.after_read = None
    kit.terminal.set_screen("/Sessions/1", TONIGHTS_LIMIT)
    kit.clock.advance(1)
    assert kit.supervisor.tick()[0].allowed
    assert len(kit.sent) == 1
    retried = kit.supervisor.store.get_episode(session.retry_episode_key)
    assert retried is not None
    assert retried.attempts == 1
