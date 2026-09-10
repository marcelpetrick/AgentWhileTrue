from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from agent_watch.summary import render_summary

NOW = datetime(2026, 9, 10, 12, 0, tzinfo=UTC)


def _line(at: str, body: str) -> str:
    stamp = datetime.fromisoformat(at.replace("Z", "+00:00")).astimezone()
    return f"{stamp.strftime('%Y-%m-%d %H:%M:%S,%f')[:-3]} INFO {body}\n"


def test_summary_counts_safe_event_categories_and_provider_wait(tmp_path: Path) -> None:
    path = tmp_path / "agent-watch.log"
    path.write_text(
        _line("2026-09-10T10:00:00+00:00", "event=resume_sent provider=claude session=/private")
        + _line(
            "2026-09-10T10:01:00+00:00",
            "event=resume_verified provider=claude result=resumed",
        )
        + _line(
            "2026-09-09T10:01:00+00:00",
            "event=resume_verified provider=claude result=armed-provider-wait",
        )
        + _line("2026-09-10T10:02:00+00:00", "event=resume_not_verified provider=claude")
        + _line("2026-09-10T10:03:00+00:00", "event=resume_refused provider=claude"),
    )
    text = render_summary(path, now=NOW, days=2)
    assert "Last 2 days: sent=1 verified=1 provider-wait=1 failures=1 refusals=1" in text
    assert "/private" not in text


def test_summary_reads_rotated_logs_and_ignores_future_or_malformed_lines(tmp_path: Path) -> None:
    path = tmp_path / "agent-watch.log"
    path.write_text(_line("2026-09-10T11:00:00+00:00", "event=resume_sent provider=codex"))
    path.with_name("agent-watch.log.1").write_text(
        _line("2026-09-10T09:00:00+00:00", "event=resume_send_failed provider=codex")
        + "not a structured line\n"
        + _line("2026-09-11T09:00:00+00:00", "event=resume_sent provider=codex")
    )
    text = render_summary(path, now=NOW, days=2)
    assert "Last 2 days: sent=1 verified=0 provider-wait=0 failures=1 refusals=0" in text


def test_summary_measures_clipped_session_time_and_marks_partial_coverage(tmp_path: Path) -> None:
    path = tmp_path / "agent-watch.log"
    path.write_text(
        _line(
            "2026-09-10T11:59:00+00:00",
            "event=supervision_interval start=2026-09-10T11:59:00+00:00 "
            "end=2026-09-10T12:00:00+00:00 blocked=true",
        )
    )
    text = render_summary(path, now=NOW, days=1)
    assert "Measured blocked session-time: 1m (partial coverage)" in text
    assert "Measured observed session-time: 1m (partial coverage)" in text


def test_summary_without_interval_evidence_reports_unavailable(tmp_path: Path) -> None:
    path = tmp_path / "agent-watch.log"
    path.write_text(_line("2026-09-10T11:00:00+00:00", "event=state_change reason=LIMIT_BLOCKED"))
    text = render_summary(path, now=NOW, days=1)
    assert "blocked session-time: unavailable" in text
    assert "observed session-time: unavailable" in text


def test_summary_skips_oversized_lines(tmp_path: Path) -> None:
    path = tmp_path / "agent-watch.log"
    path.write_bytes(
        (b"2026-09-10 10:00:00,000 INFO event=resume_sent provider=bad " + b"x" * 20000 + b"\n")
        + _line("2026-09-10T10:01:00+00:00", "event=resume_sent provider=claude").encode()
    )
    text = render_summary(path, now=NOW, days=1)
    assert "Last 24 hours: sent=1" in text


def test_one_day_window_is_rolling_and_unknown_verification_is_not_counted(tmp_path: Path) -> None:
    path = tmp_path / "agent-watch.log"
    path.write_text(
        _line("2026-09-09T12:00:01+00:00", "event=resume_sent provider=claude")
        + _line("2026-09-09T11:59:59+00:00", "event=resume_sent provider=claude")
        + _line("2026-09-10T11:00:00+00:00", "event=resume_verified result=other")
    )
    text = render_summary(path, now=NOW, days=1)
    assert "Last 24 hours: sent=1 verified=0" in text


def test_invalid_interval_fields_and_long_interval_are_ignored(tmp_path: Path) -> None:
    path = tmp_path / "agent-watch.log"
    path.write_text(
        _line(
            "2026-09-10T11:59:00+00:00",
            "event=supervision_interval start=2026-09-10T11:59:00+00:00 "
            "end=2026-09-10T12:00:00+00:00 blocked=maybe",
        )
        + _line(
            "2026-09-10T11:59:00+00:00",
            "event=supervision_interval start=2026-09-10T11:00:00+00:00 "
            "end=2026-09-10T12:00:00+00:00 blocked=true",
        )
        + _line(
            "2026-09-10T11:59:00+00:00",
            "event=supervision_interval start=2026-09-10T11:59:00+00:00 "
            "end=2026-09-10T12:00:00 blocked=true",
        )
    )
    text = render_summary(path, now=NOW, days=1)
    assert "session-time: unavailable" in text


def test_unconvertible_timestamp_does_not_break_report(tmp_path: Path, monkeypatch) -> None:
    from agent_watch import summary

    class BadLocalDate:
        def astimezone(self, zone):
            raise ValueError("year 0 is out of range")

    class LocalDatetime:
        @staticmethod
        def strptime(raw, fmt):
            return BadLocalDate()

    path = tmp_path / "agent-watch.log"
    path.write_text("0001-01-01 00:00:00,000 INFO event=resume_sent\n")
    monkeypatch.setattr(summary, "datetime", LocalDatetime)
    text = render_summary(path, now=NOW, days=1)
    assert "sent=0" in text
