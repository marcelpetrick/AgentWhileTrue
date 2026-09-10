"""Bounded operational summaries derived from structured event logs.

The summary is deliberately an aggregate view.  Log lines are parsed only far
enough to classify events and measure supervision intervals; no original line,
session identifier, account label, or terminal-derived value is returned.
"""

from __future__ import annotations

import re
import shlex
from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from agent_watch.logging_setup import LOG_BACKUPS

MAX_LINE_BYTES = 16 * 1024
MAX_INTERVAL_SECONDS = 180.0
_PREFIX = re.compile(
    rb"^(?P<stamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3})\s+(?P<level>\S+)\s+(?P<body>.*)$"
)
_INTERVAL_EVENTS = {"supervision_interval"}
_SENT = {"resume_sent"}
_VERIFIED = {"resume_verified"}
_FAILURES = {"resume_send_failed", "resume_not_verified", "resume_verification_failed"}
_REFUSALS = {
    "resume_cancelled_on_revalidation",
    "resume_cancelled_prompt_changed",
    "resume_declined_by_user",
    "resume_refused",
}


@dataclass(frozen=True, slots=True)
class _Event:
    at: datetime
    name: str
    fields: dict[str, str]


def _log_paths(path: Path) -> tuple[Path, ...]:
    rotated = (path.with_name(f"{path.name}.{number}") for number in range(1, LOG_BACKUPS + 1))
    return (path, *rotated)


def _local_stamp(raw: str, now: datetime) -> datetime | None:
    try:
        parsed = datetime.strptime(raw, "%Y-%m-%d %H:%M:%S,%f")
        # Logging timestamps use the host's local wall clock. Extreme dates
        # can parse successfully but fail while converting the local offset.
        return parsed.astimezone(UTC).astimezone(now.tzinfo or UTC)
    except (ValueError, OverflowError, OSError):
        return None


def _events(path: Path, *, now: datetime, start: datetime) -> Iterator[_Event]:
    for logfile in _log_paths(path):
        try:
            with logfile.open("rb") as handle:
                while True:
                    raw = handle.readline(MAX_LINE_BYTES + 1)
                    if not raw:
                        break
                    if len(raw) > MAX_LINE_BYTES:
                        # Drain the remainder so the next read starts at a
                        # line boundary, without allocating the whole line.
                        while raw and not raw.endswith((b"\n", b"\r")):
                            raw = handle.readline(MAX_LINE_BYTES + 1)
                        continue
                    match = _PREFIX.match(raw.rstrip(b"\r\n"))
                    if match is None:
                        continue
                    stamp = _local_stamp(match.group("stamp").decode("ascii"), now)
                    if stamp is None or stamp < start or stamp > now:
                        continue
                    try:
                        tokens = shlex.split(match.group("body").decode("utf-8"), comments=False)
                    except (UnicodeDecodeError, ValueError):
                        continue
                    if not tokens or "=" not in tokens[0]:
                        continue
                    event_name, _, event_value = tokens[0].partition("=")
                    if event_name != "event" or not event_value:
                        continue
                    fields: dict[str, str] = {}
                    for token in tokens[1:]:
                        key, separator, value = token.partition("=")
                        if separator and key and key.isidentifier():
                            fields[key] = value
                    yield _Event(stamp, event_value, fields)
        except OSError:
            continue


def _duration(seconds: float) -> str:
    if seconds < 0:
        seconds = 0
    total = int(seconds)
    if total < 60:
        return f"{total}s"
    minutes = total // 60
    if minutes < 60:
        return f"{minutes}m" if total % 60 == 0 else f"{minutes}m {total % 60}s"
    hours, remainder = divmod(minutes, 60)
    return f"{hours}h" if remainder == 0 else f"{hours}h {remainder}m"


def _interval_measure(
    item: _Event, *, now: datetime, window_start: datetime
) -> tuple[float, float] | None:
    if item.name not in _INTERVAL_EVENTS:
        return None
    if item.fields.get("blocked", "") not in {"true", "false"}:
        return None
    try:
        start = datetime.fromisoformat(item.fields["start"])
        end = datetime.fromisoformat(item.fields["end"])
    except (KeyError, TypeError, ValueError):
        return None
    if (
        start.tzinfo is None
        or end.tzinfo is None
        or end <= start
        or (end - start).total_seconds() > MAX_INTERVAL_SECONDS
        or end > now
    ):
        return None
    clipped_start = max(start, window_start)
    if end <= clipped_start:
        return None
    seconds = (end - clipped_start).total_seconds()
    return seconds if item.fields["blocked"] == "true" else 0.0, seconds


def render_summary(path: Path, *, now: datetime, days: int) -> str:
    """Render aggregate counts and bounded supervision-time evidence."""
    retention_days = max(1, int(days))
    window_start = now - timedelta(days=retention_days)
    counts: Counter[str] = Counter()
    blocked = observed = 0.0
    interval_count = 0
    for item in _events(path, now=now, start=window_start):
        if item.name in _SENT:
            counts["sent"] += 1
        elif item.name in _VERIFIED:
            result = item.fields.get("result", "")
            if result == "resumed":
                counts["verified"] += 1
            elif result == "armed-provider-wait":
                counts["verified_wait"] += 1
        elif item.name in _FAILURES:
            counts["failures"] += 1
        elif item.name in _REFUSALS:
            counts["refusals"] += 1
        measure = _interval_measure(item, now=now, window_start=window_start)
        if measure is not None:
            interval_count += 1
            blocked += measure[0]
            observed += measure[1]

    label = "Last 24 hours" if retention_days == 1 else f"Last {retention_days} days"
    lines = [f"Operational summary ({label.lower()})"]
    lines.append(
        f"{label}: sent={counts['sent']} verified={counts['verified']} "
        f"provider-wait={counts['verified_wait']} failures={counts['failures']} "
        f"refusals={counts['refusals']}"
    )
    if not interval_count:
        lines.append("Measured blocked session-time: unavailable (no interval evidence)")
        lines.append("Measured observed session-time: unavailable (no interval evidence)")
    else:
        lines.append(f"Measured blocked session-time: {_duration(blocked)} (partial coverage)")
        lines.append(f"Measured observed session-time: {_duration(observed)} (partial coverage)")
    lines.append("Event counts use retained logs; refusal counts may be incomplete.")
    return "\n".join(lines)
