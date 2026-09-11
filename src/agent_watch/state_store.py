# SPDX-FileCopyrightText: 2026 Marcel Petrick
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Persistent state, so a restart cannot repeat an action.

The hazard is narrow and specific (vision DANGER 13): the supervisor sends
Enter, crashes before it records that, restarts, sees the same prompt and sends
Enter again. Recording the action *before* it is sent closes that window - if
the crash happens in between, the restart finds a PLANNED record for that exact
prompt fingerprint and refuses rather than repeating it.

Writes are atomic: a temporary file in the same directory, then ``os.replace``.
A half-written state file is worse than none, because it would be read back as
"nothing has been done yet".
"""

from __future__ import annotations

import json
import math
import os
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from agent_watch.states import ActionState

STATE_FILENAME = "state.json"
STATE_VERSION = 1

#: Records older than this are dropped on load. A prompt fingerprint from last
#: week cannot be the prompt on screen now, and unbounded growth in a file that
#: is rewritten on every action is its own problem.
RECORD_TTL_SECONDS = 24 * 3600.0


@dataclass(slots=True)
class ActionRecord:
    """One resume attempt, through its whole lifecycle."""

    key: str
    provider: str
    session: str
    process: str
    state: ActionState
    attempts: int = 0
    planned_at: str = ""
    updated_at: str = ""
    result: str = ""

    @property
    def is_settled(self) -> bool:
        return self.state in {ActionState.VERIFIED, ActionState.FAILED}


@dataclass(slots=True)
class RetryEpisode:
    """A process-bound retry budget that survives prompt screen changes."""

    key: str
    provider: str
    session: str
    process: str
    prompt_key: str
    reset_at: str
    first_seen_at: str
    attempts: int = 0
    next_retry_at: str = ""
    pending_key: str = ""
    completed: bool = False
    exhausted: bool = False


def _now_text() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


@dataclass(slots=True)
class StateStore:
    """A small, atomically written JSON file of action records."""

    path: Path
    records: dict[str, ActionRecord] = field(default_factory=dict)
    episodes: dict[str, RetryEpisode] = field(default_factory=dict)
    retry_state_valid: bool = True

    @classmethod
    def in_directory(cls, directory: Path) -> StateStore:
        return cls(path=directory / STATE_FILENAME)

    # -- persistence -------------------------------------------------------

    def load(self, *, now: datetime | None = None) -> StateStore:
        """Read compatible records; corrupted retry evidence disables timed trials."""
        moment = now or datetime.now(UTC)
        try:
            document = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            self.records = {}
            self.episodes = {}
            self.retry_state_valid = True
            return self
        except (OSError, ValueError):
            self.records = {}
            self.episodes = {}
            self.retry_state_valid = False
            return self
        if (
            not isinstance(document, dict)
            or type(document.get("version")) is not int
            or document.get("version") != STATE_VERSION
        ):
            self.records = {}
            self.episodes = {}
            self.retry_state_valid = False
            return self
        raw_actions = document.get("actions", [])
        if not isinstance(raw_actions, list):
            self.records = {}
            self.episodes = {}
            self.retry_state_valid = False
            return self
        records: dict[str, ActionRecord] = {}
        actions_valid = True
        for raw in raw_actions:
            try:
                record = ActionRecord(**{**raw, "state": ActionState(raw["state"])})
            except (TypeError, ValueError, KeyError):
                actions_valid = False
                continue
            if (
                not all(
                    isinstance(value, str)
                    for value in (
                        record.key,
                        record.updated_at,
                        record.provider,
                        record.session,
                        record.process,
                    )
                )
                or not record.key
                or type(record.attempts) is not int
                or record.attempts < 0
            ):
                actions_valid = False
                continue
            if not _expired(record, moment):
                records[record.key] = record
        self.records = records
        raw_episodes = document.get("episodes", [])
        episodes: dict[str, RetryEpisode] = {}
        saved_validity = document.get("retry_state_valid", True)
        valid = (
            actions_valid
            and type(saved_validity) is bool
            and saved_validity
            and isinstance(raw_episodes, list)
        )
        if valid:
            for raw in raw_episodes:
                episode = _parse_episode(raw)
                if episode is None or episode.key in episodes:
                    valid = False
                    break
                episodes[episode.key] = episode
        self.episodes = episodes if valid else {}
        self.retry_state_valid = valid
        return self

    def save(self) -> None:
        """Write the state file atomically, owner-only."""
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        document = {
            "version": STATE_VERSION,
            "actions": [asdict(record) for record in self.records.values()],
            "episodes": [asdict(episode) for episode in self.episodes.values()],
            "retry_state_valid": self.retry_state_valid,
        }
        descriptor, name = tempfile.mkstemp(dir=self.path.parent, prefix=f".{self.path.name}.")
        temporary = Path(name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(document, handle, indent=2, sort_keys=True, default=str)
                handle.flush()
                # fsync before the rename: an atomic rename of unflushed data
                # would still leave a truncated file after a power loss.
                os.fsync(handle.fileno())
            temporary.chmod(0o600)
            temporary.replace(self.path)
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise

    # -- lifecycle ---------------------------------------------------------

    def plan(self, key: str, *, provider: str, session: str, process: str) -> ActionRecord:
        """Record an action as PLANNED and persist it *before* sending."""
        existing = self.records.get(key)
        attempts = existing.attempts if existing else 0
        record = ActionRecord(
            key=key,
            provider=provider,
            session=session,
            process=process,
            state=ActionState.PLANNED,
            attempts=attempts,
            planned_at=existing.planned_at if existing else _now_text(),
            updated_at=_now_text(),
        )
        self.records[key] = record
        self.save()
        return record

    def mark(self, key: str, state: ActionState, *, result: str = "") -> ActionRecord | None:
        record = self.records.get(key)
        if record is None:
            return None
        if state is ActionState.SENT:
            record.attempts += 1
        record.state = state
        record.result = result
        record.updated_at = _now_text()
        self.save()
        return record

    # -- queries -----------------------------------------------------------

    def attempts_for(self, key: str) -> int:
        record = self.records.get(key)
        return record.attempts if record else 0

    def already_actioned(self) -> frozenset[str]:
        """Keys that must not be actioned again.

        PLANNED counts. A PLANNED record that was never marked SENT is the
        crash-in-between case, and the safe reading of it is "it may already
        have been typed".
        """
        return frozenset(
            key
            for key, record in self.records.items()
            if record.state in {ActionState.PLANNED, ActionState.SENT, ActionState.VERIFIED}
        )

    def forget(self, key: str) -> None:
        if self.records.pop(key, None) is not None:
            self.save()

    # -- persistent retry episodes ---------------------------------------

    def ensure_episode(
        self,
        key: str,
        *,
        provider: str,
        session: str,
        process: str,
        prompt_key: str,
        reset_at: str,
        first_seen_at: str,
    ) -> RetryEpisode:
        existing = self.episodes.get(key)
        if existing is not None:
            return existing
        episode = RetryEpisode(
            key=key,
            provider=provider,
            session=session,
            process=process,
            prompt_key=prompt_key,
            reset_at=reset_at,
            first_seen_at=first_seen_at,
        )
        if _parse_episode(asdict(episode)) is None:
            raise ValueError("invalid retry episode")
        self.episodes[key] = episode
        self.save()
        return episode

    def get_episode(self, key: str) -> RetryEpisode | None:
        return self.episodes.get(key)

    def find_episode(
        self, *, provider: str, session: str, process: str, prompt_key: str
    ) -> RetryEpisode | None:
        matches = (
            episode
            for episode in self.episodes.values()
            if not episode.completed
            and episode.provider == provider
            and episode.session == session
            and episode.process == process
            and episode.prompt_key == prompt_key
        )
        return max(matches, key=lambda item: _timestamp(item.reset_at), default=None)

    def reserve_episode_attempt(self, key: str, action_key: str) -> RetryEpisode:
        episode = self.episodes[key]
        if not isinstance(action_key, str) or not action_key:
            raise ValueError("invalid pending action key")
        episode.attempts += 1
        episode.pending_key = action_key
        self.save()
        return episode

    def plan_episode_attempt(
        self,
        key: str,
        action_key: str,
        *,
        provider: str,
        session: str,
        process: str,
    ) -> tuple[RetryEpisode, ActionRecord]:
        """Atomically reserve an episode attempt and persist its action intent."""
        episode = self.episodes[key]
        existing = self.records.get(action_key)
        reusable = existing is not None and (
            existing.state is ActionState.FAILED
            and existing.attempts == 0
            and existing.provider == provider
            and existing.session == session
            and existing.process == process
        )
        if (
            not isinstance(action_key, str)
            or not action_key
            or episode.pending_key
            or episode.completed
            or episode.exhausted
            or (existing is not None and not reusable)
        ):
            raise ValueError("invalid episode attempt reservation")
        candidate = RetryEpisode(**asdict(episode))
        candidate.attempts += 1
        candidate.pending_key = action_key
        if _parse_episode(asdict(candidate)) is None:
            raise ValueError("invalid episode attempt reservation")
        record = ActionRecord(
            key=action_key,
            provider=provider,
            session=session,
            process=process,
            state=ActionState.PLANNED,
            planned_at=existing.planned_at if existing is not None else _now_text(),
            updated_at=_now_text(),
        )
        self.episodes[key] = candidate
        self.records[action_key] = record
        self.save()
        return candidate, record

    def release_unsent_episode_attempt(
        self, key: str, action_key: str, *, result: str
    ) -> RetryEpisode:
        """Atomically release a reservation proven not to have reached sendText."""
        episode = self.episodes[key]
        record = self.records.get(action_key)
        if (
            episode.pending_key != action_key
            or episode.attempts <= 0
            or record is None
            or record.state is not ActionState.PLANNED
        ):
            raise ValueError("invalid unsent episode attempt release")
        candidate = RetryEpisode(**asdict(episode))
        candidate.attempts -= 1
        candidate.pending_key = ""
        if _parse_episode(asdict(candidate)) is None:
            raise ValueError("invalid unsent episode attempt release")
        failed = ActionRecord(**asdict(record))
        failed.state = ActionState.FAILED
        failed.result = result
        failed.updated_at = _now_text()
        self.episodes[key] = candidate
        self.records[action_key] = failed
        self.save()
        return candidate

    def update_episode(
        self,
        key: str,
        *,
        next_retry_at: str | None = None,
        completed: bool | None = None,
        exhausted: bool | None = None,
        pending_key: str | None = None,
    ) -> RetryEpisode:
        episode = self.episodes[key]
        candidate = RetryEpisode(**asdict(episode))
        if next_retry_at is not None:
            candidate.next_retry_at = next_retry_at
        if completed is not None:
            candidate.completed = completed
        if exhausted is not None:
            candidate.exhausted = exhausted
        if pending_key is not None:
            candidate.pending_key = pending_key
        if _parse_episode(asdict(candidate)) is None:
            raise ValueError("invalid retry episode update")
        self.episodes[key] = candidate
        self.save()
        return candidate


def _expired(record: ActionRecord, now: datetime) -> bool:
    try:
        updated = datetime.fromisoformat(record.updated_at)
    except ValueError:
        return True
    if updated.tzinfo is None:
        updated = updated.replace(tzinfo=UTC)
    return (now - updated).total_seconds() > RECORD_TTL_SECONDS


def _timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or not math.isfinite(parsed.timestamp()):
        raise ValueError("timestamp must be finite and timezone-aware")
    return parsed


def _parse_episode(raw: object) -> RetryEpisode | None:
    if not isinstance(raw, dict):
        return None
    try:
        episode = RetryEpisode(**raw)
        if not all(
            isinstance(value, str) and value
            for value in (
                episode.key,
                episode.provider,
                episode.session,
                episode.process,
            )
        ):
            return None
        if not (
            isinstance(episode.prompt_key, str)
            and len(episode.prompt_key) == 64
            and all(character in "0123456789abcdef" for character in episode.prompt_key)
        ):
            return None
        _timestamp(episode.reset_at)
        _timestamp(episode.first_seen_at)
        if episode.next_retry_at:
            _timestamp(episode.next_retry_at)
        if type(episode.attempts) is not int or episode.attempts < 0:
            return None
        if type(episode.completed) is not bool or type(episode.exhausted) is not bool:
            return None
        if not isinstance(episode.next_retry_at, str) or not isinstance(episode.pending_key, str):
            return None
    except (TypeError, ValueError, OverflowError):
        return None
    return episode
