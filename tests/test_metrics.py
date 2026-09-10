# SPDX-FileCopyrightText: 2026 Marcel Petrick
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Sampling must never turn downtime into blocked session time."""

from datetime import UTC, datetime, timedelta

from agent_watch.fsm import SupervisedSession
from agent_watch.metrics import ObservationMetrics
from agent_watch.proc import ProcessIdentity
from agent_watch.terminal.base import SessionRef

NOW = datetime(2026, 9, 10, tzinfo=UTC)


class RecordingLog:
    def __init__(self):
        self.rows = []

    def info(self, event, **fields):
        self.rows.append((event, fields))


def test_metrics_exclude_pause_unknown_time_jumps_and_unsampled_waits() -> None:
    log = RecordingLog()
    metrics = ObservationMetrics(log)
    session = SupervisedSession(
        SessionRef("konsole", "org.kde.konsole-1", "/Sessions/1"),
        ProcessIdentity(123, 1, "pts/1", "/bin/claude"),
        "claude",
        observed_state="LIMIT_BLOCKED",
        observed_at=NOW,
    )

    def sample(seconds, monotonic=None):
        session.observed_at = NOW + timedelta(seconds=seconds)
        metrics.record([session], monotonic=seconds if monotonic is None else monotonic, max_gap=4)

    sample(0)
    sample(2)
    sample(4)
    metrics.reset()  # pause flushes exactly four observed seconds
    sample(100)
    sample(102)
    sample(200)  # suspend / missing observations must not add 98 seconds
    sample(202, monotonic=210)  # wall/monotonic divergence is not elapsed supervision
    session.observed_state = "unrecognized"
    sample(204)
    metrics.reset()
    assert [row[1]["end"] - row[1]["start"] for row in log.rows] == [
        timedelta(seconds=4),
        timedelta(seconds=2),
    ]
    assert all(set(row[1]) == {"start", "end", "blocked"} for row in log.rows)


def test_metrics_flush_periodically_and_do_not_count_repeated_cached_observation() -> None:
    log = RecordingLog()
    metrics = ObservationMetrics(log)
    session = SupervisedSession(
        SessionRef("konsole", "org.kde.konsole-1", "/Sessions/1"),
        ProcessIdentity(123, 1, "pts/1", "/bin/claude"),
        "claude",
        observed_state="ACTIVE",
    )
    for second in range(0, 65, 2):
        session.observed_at = NOW + timedelta(seconds=second)
        metrics.record([session], monotonic=second, max_gap=4)
    metrics.record([session], monotonic=70, max_gap=4)
    metrics.record([], monotonic=72, max_gap=4)
    assert len(log.rows) == 2
    assert sum((fields["end"] - fields["start"]).total_seconds() for _, fields in log.rows) == 64
    assert all(not fields["blocked"] for _, fields in log.rows)


def test_cached_observation_after_pause_cannot_seed_measured_time() -> None:
    log = RecordingLog()
    metrics = ObservationMetrics(log)
    session = SupervisedSession(
        SessionRef("konsole", "org.kde.konsole-1", "/Sessions/1"),
        ProcessIdentity(123, 1, "pts/1", "/bin/claude"),
        "claude",
        observed_state="LIMIT_BLOCKED",
        observed_at=NOW,
        decision_at=NOW,
    )
    metrics.record([session], monotonic=0, max_gap=4)
    metrics.reset()
    session.decision_at = NOW + timedelta(seconds=1)
    metrics.record([session], monotonic=1, max_gap=4)  # resumed but timer skipped observation
    session.observed_at = session.decision_at = NOW + timedelta(seconds=2)
    metrics.record([session], monotonic=2, max_gap=4)
    metrics.reset()
    assert log.rows == []


def test_similar_session_and_pid_suffixes_stay_independent() -> None:
    log = RecordingLog()
    metrics = ObservationMetrics(log)
    sessions = [
        SupervisedSession(
            SessionRef("konsole", "org.kde.konsole-1", f"/Sessions/{suffix}"),
            ProcessIdentity(pid, 1, "pts/1", "/bin/claude"),
            "claude",
            observed_state="LIMIT_BLOCKED",
            observed_at=NOW,
        )
        for suffix, pid in ((1, 23), (12, 3))
    ]
    metrics.record(sessions, monotonic=0, max_gap=4)
    for session in sessions:
        session.observed_at = NOW + timedelta(seconds=2)
    metrics.record(sessions, monotonic=2, max_gap=4)
    metrics.reset()
    assert len(log.rows) == 2
