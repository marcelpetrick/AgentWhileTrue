# SPDX-FileCopyrightText: 2026 Marcel Petrick
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for persistent action state."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from agent_watch.state_store import ActionRecord, RetryEpisode, StateStore
from agent_watch.states import ActionState

KEY = "abc123"
PROMPT_KEY = "a" * 64
RESET = "2026-09-10T21:52:00+02:00"
FIRST_SEEN = "2026-09-10T21:50:52+02:00"


def _store(tmp_path: Path) -> StateStore:
    return StateStore.in_directory(tmp_path).load()


def test_a_planned_action_survives_a_restart(tmp_path: Path) -> None:
    # DANGER 13: the crash happens between sending and recording. Recording
    # first means the restart sees PLANNED and refuses.
    store = _store(tmp_path)
    store.plan(KEY, provider="claude", session="/Sessions/1", process="15102:987")
    reloaded = _store(tmp_path)
    assert KEY in reloaded.already_actioned()
    assert reloaded.records[KEY].state is ActionState.PLANNED


def test_lifecycle_transitions_are_recorded(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.plan(KEY, provider="claude", session="/Sessions/1", process="15102:987")
    store.mark(KEY, ActionState.SENT)
    store.mark(KEY, ActionState.VERIFIED, result="resumed")
    record = _store(tmp_path).records[KEY]
    assert record.state is ActionState.VERIFIED
    assert record.result == "resumed"
    assert record.is_settled


def test_attempts_increment_only_on_send(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.plan(KEY, provider="claude", session="/Sessions/1", process="15102:987")
    assert store.attempts_for(KEY) == 0
    store.mark(KEY, ActionState.SENT)
    store.mark(KEY, ActionState.FAILED, result="prompt-still-visible")
    assert store.attempts_for(KEY) == 1
    store.plan(KEY, provider="claude", session="/Sessions/1", process="15102:987")
    store.mark(KEY, ActionState.SENT)
    assert store.attempts_for(KEY) == 2


def test_a_failed_action_is_not_blocked_from_retrying(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.plan(KEY, provider="claude", session="/Sessions/1", process="15102:987")
    store.mark(KEY, ActionState.SENT)
    store.mark(KEY, ActionState.FAILED)
    assert KEY not in store.already_actioned()


def test_writes_are_atomic_and_leave_no_temporary_files(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.plan(KEY, provider="claude", session="/Sessions/1", process="15102:987")
    names = {path.name for path in tmp_path.iterdir()}
    assert names == {"state.json"}


def test_state_file_is_owner_only(tmp_path: Path) -> None:
    store = StateStore.in_directory(tmp_path / "nested").load()
    store.plan(KEY, provider="claude", session="/Sessions/1", process="15102:987")
    assert store.path.stat().st_mode & 0o777 == 0o600


def test_a_corrupt_state_file_starts_empty_rather_than_refusing_to_run(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    path.write_text("{not json at all")
    assert _store(tmp_path).records == {}


def test_a_state_file_from_a_future_version_is_ignored(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    path.write_text(json.dumps({"version": 99, "actions": [{"key": "x"}]}))
    assert _store(tmp_path).records == {}


def test_stale_records_are_dropped_on_load(tmp_path: Path) -> None:
    # Yesterday's prompt fingerprint cannot be today's screen.
    old = ActionRecord(
        key=KEY,
        provider="claude",
        session="/Sessions/1",
        process="15102:987",
        state=ActionState.VERIFIED,
        updated_at=(datetime.now(UTC) - timedelta(days=3)).isoformat(timespec="seconds"),
    )
    store = StateStore.in_directory(tmp_path)
    store.records = {KEY: old}
    store.save()
    assert _store(tmp_path).records == {}


def test_malformed_records_are_skipped_not_fatal(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    path.write_text(json.dumps({"version": 1, "actions": [{"key": "x"}, {"nonsense": True}]}))
    assert _store(tmp_path).records == {}


def test_forget_removes_a_record(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.plan(KEY, provider="claude", session="/Sessions/1", process="15102:987")
    store.forget(KEY)
    assert _store(tmp_path).records == {}


def _episode(store: StateStore, key: str = "episode-one") -> RetryEpisode:
    return store.ensure_episode(
        key,
        provider="codex",
        session="org.kde.konsole-1:/Sessions/2",
        process="15102:987:pts/3",
        prompt_key=PROMPT_KEY,
        reset_at=RESET,
        first_seen_at=FIRST_SEEN,
    )


def test_retry_attempts_survive_restart_and_screen_action_key_changes(tmp_path: Path) -> None:
    store = _store(tmp_path)
    episode = _episode(store)
    assert episode.attempts == 0
    store.reserve_episode_attempt(episode.key, "screen-fingerprint-one")
    reloaded = _store(tmp_path)
    reloaded.reserve_episode_attempt(episode.key, "screen-fingerprint-two")
    restarted = _store(tmp_path).get_episode(episode.key)
    assert restarted is not None
    assert restarted.attempts == 2
    assert restarted.pending_key == "screen-fingerprint-two"


def test_reservation_is_persisted_before_a_send_can_happen(tmp_path: Path) -> None:
    store = _store(tmp_path)
    episode = _episode(store)
    reserved = store.reserve_episode_attempt(episode.key, "planned-action")
    assert reserved.attempts == 1
    assert reserved.pending_key == "planned-action"
    after_crash = _store(tmp_path).get_episode(episode.key)
    assert after_crash is not None
    assert (after_crash.attempts, after_crash.pending_key) == (1, "planned-action")


def test_episode_reservation_and_planned_action_are_one_persisted_transaction(
    tmp_path: Path, monkeypatch
) -> None:
    store = _store(tmp_path)
    episode = _episode(store)
    saves = 0
    real_save = StateStore.save

    def counted_save(current: StateStore) -> None:
        nonlocal saves
        saves += 1
        real_save(current)

    monkeypatch.setattr(StateStore, "save", counted_save)
    reserved, record = store.plan_episode_attempt(
        episode.key,
        "planned-action",
        provider="codex",
        session=episode.session,
        process=episode.process,
    )

    assert saves == 1
    assert reserved.attempts == 1
    assert reserved.pending_key == record.key
    assert record.state is ActionState.PLANNED
    reloaded = _store(tmp_path)
    assert reloaded.episodes[episode.key].pending_key == "planned-action"
    assert reloaded.records["planned-action"].state is ActionState.PLANNED


def test_known_unsent_attempt_release_restores_budget_atomically(tmp_path: Path) -> None:
    store = _store(tmp_path)
    episode = _episode(store)
    store.plan_episode_attempt(
        episode.key,
        "planned-action",
        provider="codex",
        session=episode.session,
        process=episode.process,
    )

    released = store.release_unsent_episode_attempt(
        episode.key, "planned-action", result="prompt-changed"
    )

    assert released.attempts == 0
    assert released.pending_key == ""
    reloaded = _store(tmp_path)
    assert reloaded.episodes[episode.key].attempts == 0
    assert reloaded.records["planned-action"].state is ActionState.FAILED
    assert reloaded.records["planned-action"].result == "prompt-changed"

    retried, planned = reloaded.plan_episode_attempt(
        episode.key,
        "planned-action",
        provider="codex",
        session=episode.session,
        process=episode.process,
    )
    assert retried.attempts == 1
    assert planned.state is ActionState.PLANNED
    assert planned.attempts == 0


def test_episode_updates_schedule_and_terminal_outcomes(tmp_path: Path) -> None:
    store = _store(tmp_path)
    episode = _episode(store)
    due = "2026-09-10T21:52:03+02:00"
    updated = store.update_episode(
        episode.key,
        next_retry_at=due,
        exhausted=True,
        pending_key="",
    )
    assert updated.next_retry_at == due
    assert updated.exhausted
    assert updated.pending_key == ""
    assert (
        store.find_episode(
            provider="codex",
            session=episode.session,
            process=episode.process,
            prompt_key=PROMPT_KEY,
        )
        == updated
    )
    store.update_episode(episode.key, completed=True)
    assert (
        store.find_episode(
            provider="codex",
            session=episode.session,
            process=episode.process,
            prompt_key=PROMPT_KEY,
        )
        is None
    )


def test_latest_matching_episode_is_bound_to_session_process_and_prompt(tmp_path: Path) -> None:
    store = _store(tmp_path)
    older = _episode(store, "older")
    newer = store.ensure_episode(
        "newer",
        provider="codex",
        session=older.session,
        process=older.process,
        prompt_key=PROMPT_KEY,
        reset_at="2026-09-10T22:52:00+02:00",
        first_seen_at=FIRST_SEEN,
    )
    _episode(store, "different-binding")
    store.episodes["different-binding"].process = "replacement:process"
    store.save()
    assert (
        store.find_episode(
            provider="codex",
            session=older.session,
            process=older.process,
            prompt_key=PROMPT_KEY,
        )
        == newer
    )
    assert (
        store.find_episode(
            provider="codex",
            session=older.session,
            process="replacement:process",
            prompt_key=PROMPT_KEY,
        ).key
        == "different-binding"
    )


def test_old_version_one_state_without_episodes_is_valid(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    path.write_text(json.dumps({"version": 1, "actions": []}))
    store = _store(tmp_path)
    assert store.retry_state_valid
    assert store.episodes == {}


def test_missing_state_is_a_valid_empty_retry_store(tmp_path: Path) -> None:
    store = _store(tmp_path)
    assert store.retry_state_valid
    assert store.episodes == {}


def test_malformed_entire_state_invalidates_retry_state(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    path.write_text("{broken")
    store = _store(tmp_path)
    assert not store.retry_state_valid
    assert store.episodes == {}

    # A later action lifecycle write must not erase the fail-closed condition.
    store.plan(KEY, provider="claude", session="session", process="process")
    assert not _store(tmp_path).retry_state_valid


def test_malformed_actions_container_invalidates_retry_state(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    path.write_text(json.dumps({"version": 1, "actions": {"not": "a list"}}))
    assert not _store(tmp_path).retry_state_valid


def test_one_malformed_episode_invalidates_all_retry_state(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    valid = {
        "key": "valid",
        "provider": "codex",
        "session": "session",
        "process": "process",
        "prompt_key": PROMPT_KEY,
        "reset_at": RESET,
        "first_seen_at": FIRST_SEEN,
    }
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "actions": [],
                "episodes": [valid, {**valid, "key": "bad", "attempts": -1}],
            }
        )
    )
    store = _store(tmp_path)
    assert not store.retry_state_valid
    assert store.episodes == {}


def test_retry_episode_rejects_naive_timestamps_and_non_hash_prompt(tmp_path: Path) -> None:
    store = _store(tmp_path)
    with pytest.raises(ValueError, match="invalid retry episode"):
        store.ensure_episode(
            "bad",
            provider="codex",
            session="session",
            process="process",
            prompt_key="terminal text",
            reset_at="2026-09-10T21:52:00",
            first_seen_at=FIRST_SEEN,
        )
