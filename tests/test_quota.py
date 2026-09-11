# SPDX-FileCopyrightText: 2026 Marcel Petrick
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for provider quota sources.

The fixtures are trimmed copies of real documents: a Codex session rollout event
as written by Codex CLI 0.153.2, and the status-line payload Claude Code hands
its status-line command.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from agent_watch import quota
from agent_watch.quota import (
    Availability,
    ClaudeStatuslineSource,
    CodexRolloutSource,
    NullSource,
    QuotaSnapshot,
    QuotaWindow,
)

NOW = datetime(2026, 9, 5, 20, 50, tzinfo=UTC)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -1, True, "broken"])
def test_malformed_window_never_means_available(tmp_path, monkeypatch, value) -> None:
    document = json.loads(json.dumps(CLAUDE_STATUSLINE))
    document["seven_day"]["used_percentage"] = value
    path = tmp_path / "claude.json"
    path.write_text(json.dumps(document))
    assert ClaudeStatuslineSource(path).snapshot().availability is Availability.UNKNOWN

    event = json.loads(json.dumps(CODEX_EVENT))
    event["payload"]["rate_limits"]["secondary"]["used_percent"] = value
    rollout = tmp_path / "rollout.jsonl"
    rollout.write_text(json.dumps(event))
    monkeypatch.setattr(quota, "find_codex_rollout", lambda pid: rollout)
    assert CodexRolloutSource().snapshot(pid=1).availability is Availability.UNKNOWN


CODEX_EVENT = {
    "timestamp": "2026-09-05T20:50:00.073Z",
    "type": "event_msg",
    "payload": {
        "type": "token_count",
        "rate_limits": {
            "limit_id": "codex",
            "primary": {"used_percent": 20.0, "window_minutes": 300, "resets_at": 1788527587},
            "secondary": {"used_percent": 72.0, "window_minutes": 10080, "resets_at": 1788776333},
            "credits": {"has_credits": False, "unlimited": False, "balance": "0"},
            "plan_type": "plus",
            "rate_limit_reached_type": None,
        },
    },
}

CLAUDE_STATUSLINE = {
    "source": "claude",
    "updated_at": 1788641342,
    "five_hour": {"used_percentage": 57.0, "resets_at": 1788657600},
    "seven_day": {"used_percentage": 40.0, "resets_at": 1788674400},
}


def _write_rollout(tmp_path: Path, *events: dict) -> Path:
    path = tmp_path / "rollout-2026-09-05T20-00-00-abc.jsonl"
    path.write_text("".join(json.dumps(event) + "\n" for event in events), encoding="utf-8")
    return path


def _write_account_rollout(root: Path, account_id: str, event: dict) -> Path:
    root.mkdir()
    auth = root / "auth.json"
    auth.write_text(json.dumps({"tokens": {"account_id": account_id}}))
    auth.chmod(0o600)
    path = root / "sessions/2026/09/05/rollout-live.jsonl"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(event) + "\n")
    return path


def _attach_rollouts(proc: Path, pid: int, *rollouts: Path, codex_home: Path | None = None) -> None:
    process = proc / str(pid)
    (process / "task" / str(pid)).mkdir(parents=True)
    (process / "task" / str(pid) / "children").write_text("")
    (process / "environ").write_bytes(
        f"CODEX_HOME={codex_home}\0".encode() if codex_home is not None else b""
    )
    fd = process / "fd"
    fd.mkdir()
    for number, rollout in enumerate(rollouts, start=10):
        (fd / str(number)).symlink_to(rollout)


def test_codex_rollout_is_parsed_into_windows(tmp_path: Path, monkeypatch) -> None:
    path = _write_rollout(tmp_path, CODEX_EVENT)
    monkeypatch.setattr(quota, "find_codex_rollout", lambda pid: path)
    snapshot = CodexRolloutSource().snapshot(pid=123)
    assert snapshot.availability is Availability.AVAILABLE
    assert {window.scope for window in snapshot.windows} == {"session", "weekly"}
    assert snapshot.exhausted_scopes == frozenset()


def test_codex_rollout_is_found_below_the_node_launcher(tmp_path: Path, monkeypatch) -> None:
    proc = tmp_path / "proc"
    child_file = proc / "123/task/123/children"
    child_file.parent.mkdir(parents=True)
    child_file.write_text("456\n")
    (proc / "123/environ").write_bytes(f"CODEX_HOME={tmp_path}\0".encode())
    (proc / "456/task/456").mkdir(parents=True)
    (proc / "456/task/456/children").write_text("")
    fd = proc / "456/fd"
    fd.mkdir(parents=True)
    rollout = tmp_path / "sessions/2026/09/05/rollout-live.jsonl"
    rollout.parent.mkdir(parents=True)
    rollout.write_text(json.dumps(CODEX_EVENT) + "\n")
    (fd / "9").symlink_to(rollout)
    monkeypatch.setattr(quota, "PROC", proc)

    assert quota.find_codex_rollout(123) == rollout
    assert CodexRolloutSource().snapshot(pid=123).availability is Availability.AVAILABLE


def test_codex_selects_freshest_windowed_event_across_open_descriptors(
    tmp_path: Path, monkeypatch
) -> None:
    older = json.loads(json.dumps(CODEX_EVENT))
    older["timestamp"] = "2026-09-05T18:00:00Z"
    newer = json.loads(json.dumps(CODEX_EVENT))
    newer["timestamp"] = "2026-09-05T20:55:00Z"
    newer["payload"]["rate_limits"]["primary"]["used_percent"] = 100.0
    home = tmp_path / "codex"
    old_rollout = _write_account_rollout(home, "account", older)
    new_rollout = home / "sessions/2026/09/05/rollout-new.jsonl"
    new_rollout.write_text(json.dumps(newer) + "\n")
    proc = tmp_path / "proc"
    _attach_rollouts(proc, 123, old_rollout, new_rollout, codex_home=home)
    monkeypatch.setattr(quota, "PROC", proc)

    assert quota.find_codex_rollout(123) == new_rollout
    snapshot = CodexRolloutSource().snapshot(pid=123)
    assert snapshot.availability is Availability.EXHAUSTED
    assert snapshot.observed_at == datetime(2026, 9, 5, 20, 55, tzinfo=UTC)


def test_codex_malformed_newer_timestamp_does_not_beat_valid_evidence(
    tmp_path: Path, monkeypatch
) -> None:
    valid = json.loads(json.dumps(CODEX_EVENT))
    malformed = json.loads(json.dumps(CODEX_EVENT))
    malformed["timestamp"] = "newer-but-not-a-timestamp"
    malformed["payload"]["rate_limits"]["primary"]["used_percent"] = 100.0
    home = tmp_path / "codex"
    valid_rollout = _write_account_rollout(home, "account", valid)
    malformed_rollout = home / "sessions/2026/09/05/rollout-malformed.jsonl"
    malformed_rollout.write_text(json.dumps(malformed) + "\n")
    os.utime(malformed_rollout, (2_000_000_000, 2_000_000_000))
    proc = tmp_path / "proc"
    _attach_rollouts(proc, 123, valid_rollout, malformed_rollout, codex_home=home)
    monkeypatch.setattr(quota, "PROC", proc)

    assert quota.find_codex_rollout(123) == valid_rollout


def test_codex_uses_mtime_only_when_no_rollout_has_timestamped_evidence(
    tmp_path: Path, monkeypatch
) -> None:
    first = json.loads(json.dumps(CODEX_EVENT))
    second = json.loads(json.dumps(CODEX_EVENT))
    first["timestamp"] = "invalid"
    second["timestamp"] = "also-invalid"
    home = tmp_path / "codex"
    first_rollout = _write_account_rollout(home, "account", first)
    second_rollout = home / "sessions/2026/09/05/rollout-newest-mtime.jsonl"
    second_rollout.write_text(json.dumps(second) + "\n")
    os.utime(first_rollout, (1_000_000_000, 1_000_000_000))
    os.utime(second_rollout, (2_000_000_000, 2_000_000_000))
    proc = tmp_path / "proc"
    _attach_rollouts(proc, 123, first_rollout, second_rollout, codex_home=home)
    monkeypatch.setattr(quota, "PROC", proc)

    assert quota.find_codex_rollout(123) == second_rollout


def test_codex_rollout_discovery_does_not_cross_profile_home(tmp_path: Path, monkeypatch) -> None:
    selected = json.loads(json.dumps(CODEX_EVENT))
    other = json.loads(json.dumps(CODEX_EVENT))
    other["timestamp"] = "2026-09-05T20:59:00Z"
    other["payload"]["rate_limits"]["primary"]["used_percent"] = 100.0
    selected_home = tmp_path / "codex-selected"
    other_home = tmp_path / "codex-other"
    selected_rollout = _write_account_rollout(selected_home, "selected", selected)
    other_rollout = _write_account_rollout(other_home, "other", other)
    proc = tmp_path / "proc"
    _attach_rollouts(
        proc,
        123,
        selected_rollout,
        other_rollout,
        codex_home=selected_home,
    )
    monkeypatch.setattr(quota, "PROC", proc)

    assert quota.find_codex_rollout(123) == selected_rollout
    assert CodexRolloutSource().snapshot(pid=123).availability is Availability.AVAILABLE


def test_codex_child_with_another_explicit_profile_cannot_override_root(
    tmp_path: Path, monkeypatch
) -> None:
    selected = json.loads(json.dumps(CODEX_EVENT))
    other = json.loads(json.dumps(CODEX_EVENT))
    other["timestamp"] = "2026-09-05T20:59:00Z"
    other["payload"]["rate_limits"]["primary"]["used_percent"] = 100.0
    selected_home = tmp_path / "codex-selected"
    other_home = tmp_path / "codex-other"
    selected_rollout = _write_account_rollout(selected_home, "selected", selected)
    other_rollout = _write_account_rollout(other_home, "other", other)
    proc = tmp_path / "proc"
    _attach_rollouts(proc, 123, selected_rollout, codex_home=selected_home)
    _attach_rollouts(proc, 456, other_rollout, codex_home=other_home)
    (proc / "123/task/123/children").write_text("456\n")
    monkeypatch.setattr(quota, "PROC", proc)

    assert quota.find_codex_rollout(123) == selected_rollout
    assert CodexRolloutSource().snapshot(pid=123).availability is Availability.AVAILABLE


def test_codex_future_timestamp_does_not_outrank_current_evidence(
    tmp_path: Path, monkeypatch
) -> None:
    current = json.loads(json.dumps(CODEX_EVENT))
    current["timestamp"] = datetime.now(UTC).isoformat()
    future = json.loads(json.dumps(CODEX_EVENT))
    future["timestamp"] = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
    future["payload"]["rate_limits"]["primary"]["used_percent"] = 100.0
    home = tmp_path / "codex"
    current_rollout = _write_account_rollout(home, "account", current)
    future_rollout = home / "sessions/2026/09/05/rollout-future.jsonl"
    future_rollout.write_text(json.dumps(future) + "\n")
    proc = tmp_path / "proc"
    _attach_rollouts(proc, 123, current_rollout, future_rollout, codex_home=home)
    monkeypatch.setattr(quota, "PROC", proc)

    assert quota.find_codex_rollout(123) == current_rollout


def test_codex_non_object_event_does_not_erase_valid_windows(tmp_path: Path, monkeypatch) -> None:
    path = _write_rollout(tmp_path, CODEX_EVENT)
    with path.open("a", encoding="utf-8") as stream:
        stream.write('["rate_limits", "malformed"]\n')
    monkeypatch.setattr(quota, "find_codex_rollout", lambda pid: path)

    assert CodexRolloutSource().snapshot(pid=123).availability is Availability.AVAILABLE


def test_codex_newest_event_wins(tmp_path: Path, monkeypatch) -> None:
    older = json.loads(json.dumps(CODEX_EVENT))
    newer = json.loads(json.dumps(CODEX_EVENT))
    newer["payload"]["rate_limits"]["primary"]["used_percent"] = 100.0
    path = _write_rollout(tmp_path, older, newer)
    monkeypatch.setattr(quota, "find_codex_rollout", lambda pid: path)
    snapshot = CodexRolloutSource().snapshot(pid=123)
    assert snapshot.availability is Availability.EXHAUSTED
    assert snapshot.exhausted_scopes == {"session"}


def test_codex_transient_empty_event_falls_back_to_last_usable_state(
    tmp_path: Path, monkeypatch
) -> None:
    empty = {"timestamp": "2026-09-05T20:51:00Z", "payload": {"rate_limits": {}}}
    path = _write_rollout(tmp_path, CODEX_EVENT, empty)
    monkeypatch.setattr(quota, "find_codex_rollout", lambda pid: path)

    snapshot = CodexRolloutSource().snapshot(pid=123)
    assert snapshot.availability is Availability.AVAILABLE
    assert {window.scope for window in snapshot.windows} == {"session", "weekly"}


def test_codex_premium_event_without_windows_does_not_erase_valid_windows(
    tmp_path: Path, monkeypatch
) -> None:
    premium = {
        "timestamp": "2026-09-05T20:59:00Z",
        "payload": {"rate_limits": {"limit_id": "premium", "credits": {}}},
    }
    path = _write_rollout(tmp_path, CODEX_EVENT, premium)
    monkeypatch.setattr(quota, "find_codex_rollout", lambda pid: path)

    snapshot = CodexRolloutSource().snapshot(pid=123)
    assert snapshot.observed_at == datetime(2026, 9, 5, 20, 50, 0, 73000, tzinfo=UTC)
    assert {window.scope for window in snapshot.windows} == {"session", "weekly"}


def test_codex_reached_type_forces_exhausted(tmp_path: Path, monkeypatch) -> None:
    # The provider says a limit was reached even though no window reads 100%.
    # The provider's own verdict wins.
    event = json.loads(json.dumps(CODEX_EVENT))
    event["payload"]["rate_limits"]["rate_limit_reached_type"] = "usage_limit_reached"
    path = _write_rollout(tmp_path, event)
    monkeypatch.setattr(quota, "find_codex_rollout", lambda pid: path)
    assert CodexRolloutSource().snapshot(pid=123).availability is Availability.EXHAUSTED


def test_codex_uses_fresh_quota_from_the_same_account(tmp_path: Path, monkeypatch) -> None:
    stale_event = json.loads(json.dumps(CODEX_EVENT))
    stale_event["timestamp"] = "2026-09-05T18:00:00Z"
    stale_event["payload"]["rate_limits"]["primary"]["used_percent"] = 98.0
    fresh_event = json.loads(json.dumps(CODEX_EVENT))
    fresh_event["timestamp"] = "2026-09-05T20:55:00Z"
    fresh_event["payload"]["rate_limits"]["primary"]["used_percent"] = 4.0
    stale = _write_account_rollout(tmp_path / "codex-a", "same-account", stale_event)
    fresh = _write_account_rollout(tmp_path / "codex-b", "same-account", fresh_event)
    paths = {1: stale, 2: fresh}
    monkeypatch.setattr(quota, "find_codex_rollout", paths.get)
    source = CodexRolloutSource()

    assert source.snapshot(pid=1).observed_at == datetime(2026, 9, 5, 18, 0, tzinfo=UTC)
    assert source.snapshot(pid=2).availability is Availability.AVAILABLE
    shared = source.snapshot(pid=1)

    assert shared.availability is Availability.AVAILABLE
    assert shared.observed_at == datetime(2026, 9, 5, 20, 55, tzinfo=UTC)


def test_codex_never_shares_quota_between_accounts(tmp_path: Path, monkeypatch) -> None:
    stale_event = json.loads(json.dumps(CODEX_EVENT))
    stale_event["timestamp"] = "2026-09-05T18:00:00Z"
    fresh_event = json.loads(json.dumps(CODEX_EVENT))
    fresh_event["timestamp"] = "2026-09-05T20:55:00Z"
    stale = _write_account_rollout(tmp_path / "codex-a", "account-a", stale_event)
    fresh = _write_account_rollout(tmp_path / "codex-b", "account-b", fresh_event)
    paths = {1: stale, 2: fresh}
    monkeypatch.setattr(quota, "find_codex_rollout", paths.get)
    source = CodexRolloutSource()

    first = source.snapshot(pid=1)
    source.snapshot(pid=2)

    assert source.snapshot(pid=1) == first


def test_codex_never_shares_quota_between_rate_limit_identities(
    tmp_path: Path, monkeypatch
) -> None:
    first_event = json.loads(json.dumps(CODEX_EVENT))
    second_event = json.loads(json.dumps(CODEX_EVENT))
    second_event["timestamp"] = "2026-09-05T20:55:00Z"
    second_event["payload"]["rate_limits"]["limit_id"] = "different-model"
    first = _write_account_rollout(tmp_path / "codex-a", "same-account", first_event)
    second = _write_account_rollout(tmp_path / "codex-b", "same-account", second_event)
    paths = {1: first, 2: second}
    monkeypatch.setattr(quota, "find_codex_rollout", paths.get)
    source = CodexRolloutSource()

    original = source.snapshot(pid=1)
    source.snapshot(pid=2)

    assert source.snapshot(pid=1) == original


def test_codex_partial_first_line_after_a_tail_seek_is_tolerated(
    tmp_path: Path, monkeypatch
) -> None:
    path = _write_rollout(tmp_path, CODEX_EVENT)
    path.write_text('{"truncated": tru\n' + path.read_text(), encoding="utf-8")
    monkeypatch.setattr(quota, "find_codex_rollout", lambda pid: path)
    assert CodexRolloutSource().snapshot(pid=123).availability is Availability.AVAILABLE


def test_codex_without_a_rollout_is_unknown_not_available(monkeypatch) -> None:
    monkeypatch.setattr(quota, "find_codex_rollout", lambda pid: None)
    snapshot = CodexRolloutSource().snapshot(pid=123)
    assert snapshot.availability is Availability.UNKNOWN
    assert snapshot.note == "no-rollout-file"


def test_codex_source_without_a_pid_is_unknown() -> None:
    assert CodexRolloutSource().snapshot().availability is Availability.UNKNOWN


def test_a_broken_source_returns_unknown_rather_than_raising(tmp_path: Path, monkeypatch) -> None:
    def explode(pid: int):
        raise OSError("bus error")

    monkeypatch.setattr(quota, "find_codex_rollout", explode)
    snapshot = CodexRolloutSource().snapshot(pid=1)
    assert snapshot.availability is Availability.UNKNOWN
    assert snapshot.note.startswith("error:")


def test_claude_statusline_is_parsed(tmp_path: Path) -> None:
    path = tmp_path / "claude.json"
    path.write_text(json.dumps(CLAUDE_STATUSLINE), encoding="utf-8")
    snapshot = ClaudeStatuslineSource(path=path).snapshot()
    assert snapshot.availability is Availability.AVAILABLE
    assert {window.scope for window in snapshot.windows} == {"session", "weekly"}


def test_claude_statusline_accepts_the_utilization_spelling(tmp_path: Path) -> None:
    path = tmp_path / "claude.json"
    path.write_text(
        json.dumps({"updated_at": 1788641342, "five_hour": {"utilization": 100}}), encoding="utf-8"
    )
    snapshot = ClaudeStatuslineSource(path=path).snapshot()
    assert snapshot.exhausted_scopes == {"session"}


def test_missing_statusline_file_is_unknown(tmp_path: Path) -> None:
    snapshot = ClaudeStatuslineSource(path=tmp_path / "absent.json").snapshot()
    assert snapshot.availability is Availability.UNKNOWN


def test_corrupt_statusline_file_is_unknown(tmp_path: Path) -> None:
    path = tmp_path / "claude.json"
    path.write_text("{not json", encoding="utf-8")
    assert ClaudeStatuslineSource(path=path).snapshot().availability is Availability.UNKNOWN


def test_next_reset_is_the_last_exhausted_window() -> None:
    early = datetime(2026, 9, 5, 21, 0, tzinfo=UTC)
    late = datetime(2026, 9, 11, 10, 0, tzinfo=UTC)
    snapshot = QuotaSnapshot(
        provider="claude",
        availability=Availability.EXHAUSTED,
        source="test",
        observed_at=NOW,
        windows=(
            QuotaWindow("session", 100.0, early),
            QuotaWindow("weekly", 100.0, late),
        ),
    )
    # A five-hour reset must not unblock a spent weekly window.
    assert snapshot.next_reset == late


def test_a_healthy_window_does_not_extend_the_reset() -> None:
    snapshot = QuotaSnapshot(
        provider="claude",
        availability=Availability.EXHAUSTED,
        source="test",
        observed_at=NOW,
        windows=(
            QuotaWindow("session", 100.0, datetime(2026, 9, 5, 21, 0, tzinfo=UTC)),
            QuotaWindow("weekly", 12.0, datetime(2026, 9, 11, 10, 0, tzinfo=UTC)),
        ),
    )
    assert snapshot.next_reset == datetime(2026, 9, 5, 21, 0, tzinfo=UTC)


def test_staleness_is_detected() -> None:
    snapshot = QuotaSnapshot(
        provider="claude",
        availability=Availability.AVAILABLE,
        source="test",
        observed_at=NOW - timedelta(hours=2),
    )
    assert snapshot.is_stale(NOW)
    assert not snapshot.is_stale(NOW - timedelta(hours=2))


def test_a_snapshot_without_a_timestamp_is_stale() -> None:
    snapshot = QuotaSnapshot(provider="claude", availability=Availability.UNKNOWN, source="test")
    assert snapshot.is_stale(NOW)


def test_a_snapshot_far_in_the_future_is_stale() -> None:
    snapshot = QuotaSnapshot(
        provider="codex",
        availability=Availability.AVAILABLE,
        source="test",
        observed_at=NOW + timedelta(hours=1),
    )
    assert snapshot.is_stale(NOW)


def test_null_source_is_always_unknown() -> None:
    assert NullSource().snapshot(pid=1).availability is Availability.UNKNOWN


def test_default_sources_cover_both_providers(tmp_path: Path) -> None:
    sources = quota.default_sources(tmp_path)
    assert set(sources) == {"codex", "claude"}
