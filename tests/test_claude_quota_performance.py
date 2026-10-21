# SPDX-FileCopyrightText: 2026 Marcel Petrick
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Operation-count regressions for the process-bound Claude quota index."""

import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from agent_while_true import quota
from agent_while_true.quota import Availability, ClaudeStatuslineSource

NOW = datetime(2026, 10, 21, 12, tzinfo=UTC)


def _write(path: Path, *, pid: int = 1, start: int = 100, used: int = 10, age: int = 0) -> None:
    path.write_text(
        json.dumps(
            {
                "source": "claude",
                "process": {"pid": pid, "start_time": start},
                "updated_at": (NOW - timedelta(seconds=age)).isoformat(),
                "five_hour": {"used_percentage": used},
            }
        )
    )


@pytest.fixture
def source(tmp_path: Path, monkeypatch) -> ClaudeStatuslineSource:
    monkeypatch.setattr(quota, "read_start_time", lambda pid: 100)
    return ClaudeStatuslineSource(tmp_path / "claude.json")


def test_warm_four_session_reads_parse_only_changed_files(tmp_path, monkeypatch, source) -> None:
    for index in range(250):
        _write(tmp_path / f"claude-archive-{index}.json", pid=1000 + index, age=86400)
    for pid in range(1, 5):
        _write(tmp_path / f"claude-live-{pid}.json", pid=pid)
    original = json.loads
    parses = 0

    def counted(*args, **kwargs):
        nonlocal parses
        parses += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(quota.json, "loads", counted)
    for _ in range(2):
        for pid in range(1, 5):
            assert source.snapshot(pid=pid).availability is Availability.AVAILABLE
    assert parses == 254
    _write(tmp_path / "claude-live-4.json", pid=4, used=100)
    for pid in range(1, 5):
        expected = Availability.EXHAUSTED if pid == 4 else Availability.AVAILABLE
        assert source.snapshot(pid=pid).availability is expected
    assert parses == 255


@pytest.mark.parametrize("mutation", ["replace", "inplace", "same-size-restored-mtime"])
def test_every_snapshot_detects_file_mutation(tmp_path, source, mutation) -> None:
    path = tmp_path / "claude-live.json"
    _write(path)
    assert source.snapshot(pid=1).windows[0].used_percent == 10
    previous = path.stat()
    if mutation == "replace":
        replacement = tmp_path / "replacement.json"
        _write(replacement, used=100)
        replacement.replace(path)
    else:
        _write(path, used=90 if mutation == "same-size-restored-mtime" else 100)
        if mutation == "same-size-restored-mtime":
            assert path.stat().st_size == previous.st_size
            os.utime(path, ns=(previous.st_atime_ns, previous.st_mtime_ns))
    snapshot = source.snapshot(pid=1)
    assert snapshot.windows[0].used_percent == (90 if mutation.endswith("mtime") else 100)


def test_newer_duplicate_exhaustion_is_seen_without_waiting(tmp_path, source) -> None:
    _write(tmp_path / "claude-a.json", age=60)
    assert source.snapshot(pid=1).availability is Availability.AVAILABLE
    _write(tmp_path / "claude-b.json", used=100)
    assert source.snapshot(pid=1).availability is Availability.EXHAUSTED
    (tmp_path / "claude-a.json").unlink()
    assert source.snapshot(pid=1).availability is Availability.EXHAUSTED
    assert tmp_path / "claude-a.json" not in source._parsed


def test_deleted_cached_file_is_not_available(tmp_path, source) -> None:
    path = tmp_path / "claude-a.json"
    _write(path)
    assert source.snapshot(pid=1).availability is Availability.AVAILABLE
    path.unlink()
    assert source.snapshot(pid=1).availability is Availability.UNKNOWN
    assert not source._parsed


def test_malformed_replacement_and_new_file_never_restore_cached_availability(tmp_path, source):
    path = tmp_path / "claude-a.json"
    _write(path)
    assert source.snapshot(pid=1).availability is Availability.AVAILABLE
    path.write_text("{invalid")
    assert source.snapshot(pid=1).availability is Availability.UNKNOWN
    path.unlink()
    (tmp_path / "claude-new.json").write_text("{invalid")
    assert source.snapshot(pid=1).availability is Availability.UNKNOWN


def test_newest_malformed_windows_do_not_fall_back_to_older_available(tmp_path, source) -> None:
    _write(tmp_path / "claude-a.json", age=60)
    path = tmp_path / "claude-b.json"
    _write(path)
    path.write_text(path.read_text().replace('"used_percentage": 10', '"used_percentage": "bad"'))
    assert source.snapshot(pid=1).availability is Availability.UNKNOWN


def test_cache_never_refreshes_observation_timestamp(tmp_path, source) -> None:
    _write(tmp_path / "claude-a.json", age=3600)
    first = source.snapshot(pid=1)
    second = source.snapshot(pid=1)
    assert first == second
    assert second.observed_at == NOW - timedelta(hours=1)
    assert second.is_stale(NOW)


def test_pid_reuse_is_checked_on_cache_hits(tmp_path, monkeypatch, source) -> None:
    _write(tmp_path / "claude-a.json")
    assert source.snapshot(pid=1).availability is Availability.AVAILABLE
    monkeypatch.setattr(quota, "read_start_time", lambda pid: 200)
    assert source.snapshot(pid=1).availability is Availability.UNKNOWN


def test_pid_reuse_during_read_is_unknown(tmp_path, monkeypatch, source) -> None:
    _write(tmp_path / "claude-a.json")
    starts = iter([100, 200])
    monkeypatch.setattr(quota, "read_start_time", lambda pid: next(starts))
    assert source.snapshot(pid=1).note == "process-changed"


def test_directory_read_failure_does_not_reuse_old_available(tmp_path, monkeypatch, source):
    _write(tmp_path / "claude-a.json")
    assert source.snapshot(pid=1).availability is Availability.AVAILABLE
    original = Path.iterdir

    def denied(path):
        if path == tmp_path:
            raise PermissionError
        return original(path)

    monkeypatch.setattr(Path, "iterdir", denied)
    assert source.snapshot(pid=1).availability is Availability.UNKNOWN


def test_mutation_during_json_read_is_unknown(tmp_path, monkeypatch, source):
    path = tmp_path / "claude-a.json"
    _write(path)
    original = json.loads

    def mutate(*args, **kwargs):
        result = original(*args, **kwargs)
        _write(path, used=100)
        return result

    monkeypatch.setattr(quota.json, "loads", mutate)
    assert source.snapshot(pid=1).availability is Availability.UNKNOWN


def test_mutation_after_cached_selection_is_unknown(tmp_path, monkeypatch, source):
    path = tmp_path / "claude-a.json"
    _write(path)
    assert source.snapshot(pid=1).availability is Availability.AVAILABLE
    original = quota._file_version
    reads = 0

    def mutate(candidate):
        nonlocal reads
        if candidate == path:
            reads += 1
            if reads == 2:
                _write(path, used=100)
        return original(candidate)

    monkeypatch.setattr(quota, "_file_version", mutate)
    assert source.snapshot(pid=1).note == "statusline-changed"


def test_new_file_during_directory_scan_is_unknown(tmp_path, monkeypatch, source):
    _write(tmp_path / "claude-a.json")
    original = json.loads

    def mutate(*args, **kwargs):
        result = original(*args, **kwargs)
        _write(tmp_path / "claude-b.json", used=100)
        return result

    monkeypatch.setattr(quota.json, "loads", mutate)
    assert source.snapshot(pid=1).note == "statusline-directory-changed"


def test_normalized_cache_is_bounded_and_discards_payload(tmp_path, source, monkeypatch):
    monkeypatch.setattr(quota, "_CLAUDE_CACHE_LIMIT", 8)
    for index in range(20):
        _write(tmp_path / f"claude-{index}.json", pid=index + 1)
    source.snapshot(pid=1)
    assert len(source._parsed) == 8
    for _, record in source._parsed.values():
        assert record is not None
        assert not hasattr(record, "document")
        assert len(record.snapshot.windows) == 1


def test_missing_directory_is_unknown_and_clears_index(tmp_path, source):
    path = tmp_path / "claude-a.json"
    _write(path)
    assert source.snapshot(pid=1).availability is Availability.AVAILABLE
    path.unlink()
    tmp_path.rmdir()
    assert source.snapshot(pid=1).note == "no-statusline-file"
    assert not source._parsed


def test_unrepresentable_timestamp_only_blocks_its_bound_process(tmp_path, source):
    _write(tmp_path / "claude-a.json")
    path = tmp_path / "claude-other.json"
    _write(path, pid=2)
    path.write_text(path.read_text().replace('"2026-10-21T12:00:00+00:00"', "1e100"))
    assert source.snapshot(pid=1).availability is Availability.AVAILABLE
    assert source.snapshot(pid=2).availability is Availability.UNKNOWN
    assert source.snapshot(pid=2).note.startswith("error:")


def test_candidate_stat_failure_never_uses_cached_record(tmp_path, source, monkeypatch):
    path = tmp_path / "claude-a.json"
    _write(path)
    assert source.snapshot(pid=1).availability is Availability.AVAILABLE
    original = quota._file_version

    def gone(candidate):
        if candidate == path:
            raise FileNotFoundError
        return original(candidate)

    monkeypatch.setattr(quota, "_file_version", gone)
    assert source.snapshot(pid=1).availability is Availability.UNKNOWN
    assert path not in source._parsed


def test_file_that_grows_while_opening_is_bounded_and_unknown(tmp_path, source, monkeypatch):
    path = tmp_path / "claude-a.json"
    _write(path)
    original = Path.open

    def grow(candidate, *args, **kwargs):
        if candidate == path and args == ("rb",):
            with original(candidate, "wb") as handle:
                handle.write(b" " * (quota._CLAUDE_FILE_BYTES + 10))
        return original(candidate, *args, **kwargs)

    monkeypatch.setattr(Path, "open", grow)
    assert source.snapshot(pid=1).availability is Availability.UNKNOWN


@pytest.mark.parametrize("encoding", ["utf-16", "utf-32"])
def test_cache_does_not_expand_utf8_bridge_file_contract(tmp_path, source, encoding):
    path = tmp_path / "claude-a.json"
    _write(path)
    document = path.read_text()
    path.write_bytes(document.encode(encoding))
    assert source.snapshot(pid=1).availability is Availability.UNKNOWN
    assert source.snapshot(pid=1).availability is Availability.UNKNOWN


def test_full_cache_does_not_reparse_cached_prefix_on_every_scan(tmp_path, source, monkeypatch):
    monkeypatch.setattr(quota, "_CLAUDE_CACHE_LIMIT", 8)
    for index in range(10):
        _write(tmp_path / f"claude-{index}.json", pid=index + 1)
    original = json.loads
    parses = 0

    def counted(*args, **kwargs):
        nonlocal parses
        parses += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(quota.json, "loads", counted)
    assert source.snapshot(pid=1).availability is Availability.AVAILABLE
    assert parses == 10
    assert len(source._parsed) == 8
    cached_paths = set(source._parsed)
    excess = next(path for path in tmp_path.iterdir() if path not in cached_paths)
    for _ in range(3):
        previous = parses
        source.snapshot(pid=1)
        assert parses - previous == 2
        assert set(source._parsed) == cached_paths

    # An uncached file is still read each time: cache admission must not hide
    # a newly exhausted process simply because the bounded index is full.
    _write(excess, pid=42, used=100)
    assert source.snapshot(pid=42).availability is Availability.EXHAUSTED
    assert len(source._parsed) == 8

    # A cached file can update its own slot without evicting another one.
    cached = next(iter(cached_paths))
    _write(cached, pid=43, used=100)
    assert source.snapshot(pid=43).availability is Availability.EXHAUSTED
    assert set(source._parsed) == cached_paths

    # Deleting a cached file releases a slot for an existing uncached file.
    cached.unlink()
    source.snapshot(pid=42)
    assert len(source._parsed) == 8
    assert cached not in source._parsed


def test_transient_io_failure_is_retried_without_a_file_update(tmp_path, source, monkeypatch):
    path = tmp_path / "claude-a.json"
    _write(path)
    original = Path.open
    attempts = 0

    def unavailable_once(candidate, *args, **kwargs):
        nonlocal attempts
        if candidate == path and args == ("rb",):
            attempts += 1
            if attempts == 1:
                raise PermissionError
        return original(candidate, *args, **kwargs)

    monkeypatch.setattr(Path, "open", unavailable_once)
    assert source.snapshot(pid=1).availability is Availability.UNKNOWN
    assert source.snapshot(pid=1).availability is Availability.AVAILABLE
    assert attempts == 2


@pytest.mark.parametrize("payload", [b"\xff", '{"source":"claude"}'.encode("utf-16")])
def test_invalid_utf8_file_does_not_fall_back_to_other_available_document(
    tmp_path, source, payload
):
    _write(tmp_path / "claude-a.json")
    (tmp_path / "claude-invalid.json").write_bytes(payload)
    snapshot = source.snapshot(pid=1)
    assert snapshot.availability is Availability.UNKNOWN
    assert snapshot.note == "error:UnicodeDecodeError"
