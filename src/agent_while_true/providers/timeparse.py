# SPDX-FileCopyrightText: 2026 Marcel Petrick
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Parse the reset times that the agent CLIs print.

Machine-readable provider state is always preferred (vision DANGER 12), and this
module is the fallback for when none is available. It is deliberately strict:
anything it cannot parse with confidence returns ``None``, and a ``None`` reset
time means the supervisor waits for a provider signal instead of guessing.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

#: "resets 8:10pm (Europe/Berlin)" / "Try again at 8:10 PM"
_CLOCK_RE = re.compile(
    r"(?P<hour>\d{1,2})[:.](?P<minute>\d{2})\s*(?P<meridiem>am|pm)?"
    r"(?:\s*\((?P<tz>[A-Za-z_]+/[A-Za-z_+-]+)\))?",
    re.IGNORECASE,
)
_MONTH_NAMES = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}
_MONTH_DATE_RE = re.compile(
    r"\b(?P<month>Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|"
    r"Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|"
    r"Nov(?:ember)?|Dec(?:ember)?)\s+"
    r"(?P<day>\d{1,2})(?:st|nd|rd|th)?(?:,\s*|\s+)"
    r"(?P<year>\d{4})\s+"
    r"(?P<hour>\d{1,2})[:.](?P<minute>\d{2})\s*(?P<meridiem>am|pm)?"
    r"(?:\s*\((?P<tz>[A-Za-z_]+/[A-Za-z_+-]+)\))?",
    re.IGNORECASE,
)
_ISO_DATE_RE = re.compile(
    r"\b(?P<year>\d{4})-(?P<month>\d{2})-(?P<day>\d{2})"
    r"(?:[ T])(?P<hour>\d{1,2})[:.](?P<minute>\d{2})\s*(?P<meridiem>am|pm)?"
    r"(?:\s*\((?P<tz>[A-Za-z_]+/[A-Za-z_+-]+)\))?",
    re.IGNORECASE,
)
_DATED_TEXT_RE = re.compile(
    r"\b(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|"
    r"Dec(?:ember)?|\d{4}-\d{2}-\d{2})\b",
    re.IGNORECASE,
)
#: "resets Mon 12:00am"
_WEEKDAY_RE = re.compile(
    r"\b(?P<weekday>mon|tue|tues|wed|thu|thur|thurs|fri|sat|sun)[a-z]*\b", re.IGNORECASE
)
#: "resets in 4h51m" / "resets in 90m" / "resets in 45s"
_RELATIVE_RE = re.compile(
    r"\bin\s+(?:(?P<hours>\d+)\s*h)?\s*(?:(?P<minutes>\d+)\s*m(?!s))?\s*(?:(?P<seconds>\d+)\s*s)?",
    re.IGNORECASE,
)

_WEEKDAYS = {
    "mon": 0,
    "tue": 1,
    "tues": 1,
    "wed": 2,
    "thu": 3,
    "thur": 3,
    "thurs": 3,
    "fri": 4,
    "sat": 5,
    "sun": 6,
}

DAYS_PER_WEEK = 7
NOON = 12
HOURS_PER_DAY = 24
MINUTES_PER_HOUR = 60


def _local_zone() -> ZoneInfo | None:
    """Resolve the host's IANA zone without adding a runtime dependency."""
    try:
        target = Path("/etc/localtime").resolve()
        parts = target.parts
        marker = parts.index("zoneinfo")
        return ZoneInfo("/".join(parts[marker + 1 :]))
    except (OSError, ValueError, ZoneInfoNotFoundError):
        return None


def _zone(name: str | None, fallback: datetime) -> ZoneInfo | None:
    if not name:
        # The supervisor intentionally keeps its internal clock in UTC. Provider
        # prompts without a zone, however, display the user's local wall clock.
        # Preserve an explicitly supplied IANA zone in tests/callers and resolve
        # the machine zone when the caller uses datetime.UTC.
        return fallback.tzinfo if isinstance(fallback.tzinfo, ZoneInfo) else _local_zone()
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        return None


def _apply_meridiem(hour: int, meridiem: str | None) -> int | None:
    if meridiem is None:
        return hour if 0 <= hour < HOURS_PER_DAY else None
    lowered = meridiem.lower()
    if not 1 <= hour <= NOON:
        return None
    if lowered == "am":
        return 0 if hour == NOON else hour
    return hour if hour == NOON else hour + NOON


def parse_relative(text: str, now: datetime) -> datetime | None:
    """Parse ``resets in 4h51m`` style text into an absolute instant."""
    match = _RELATIVE_RE.search(text)
    if match is None or not any(match.group(name) for name in ("hours", "minutes", "seconds")):
        return None
    delta = timedelta(
        hours=int(match.group("hours") or 0),
        minutes=int(match.group("minutes") or 0),
        seconds=int(match.group("seconds") or 0),
    )
    if delta == timedelta(0):
        return None
    return now + delta


def _parse_explicit_date(text: str, now: datetime) -> tuple[bool, datetime | None]:
    """Return whether dated text was present and its exact instant if valid."""
    match = _MONTH_DATE_RE.search(text) or _ISO_DATE_RE.search(text)
    if match is None:
        return _DATED_TEXT_RE.search(text) is not None, None
    hour = _apply_meridiem(int(match.group("hour")), match.group("meridiem"))
    minute = int(match.group("minute"))
    if hour is None or minute >= MINUTES_PER_HOUR:
        return True, None
    zone_name = match.group("tz")
    zone = _zone(zone_name, now)
    if zone_name and zone is None:
        return True, None
    effective_zone = zone or now.tzinfo
    try:
        month_text = match.group("month")
        month = int(month_text) if month_text.isdigit() else _MONTH_NAMES[month_text[:3].lower()]
        candidate = datetime(
            int(match.group("year")),
            month,
            int(match.group("day")),
            hour,
            minute,
            tzinfo=effective_zone,
        )
    except (KeyError, ValueError):
        return True, None
    return True, candidate.astimezone(now.tzinfo)


def parse_reset(text: str, now: datetime) -> datetime | None:
    """Parse a reset instant out of one line of provider output.

    Handles these supported shapes:

    - ``resets 8:10pm (Europe/Berlin)`` - a clock time, optionally with a zone;
    - ``resets Mon 12:00am`` - a clock time on the next occurrence of a weekday;
    - ``resets in 4h51m`` - a relative offset.
    - ``Sep 10, 2026 9:52 PM`` or ``2026-09-10 21:52`` - an explicit date.

    An undated clock that has passed rolls forward; callers must anchor repeated
    observations to the first sighting. Explicit dates never roll forward.
    """
    dated, explicit = _parse_explicit_date(text, now)
    if dated:
        return explicit

    if (relative := parse_relative(text, now)) is not None:
        return relative

    clock = _CLOCK_RE.search(text)
    if clock is None:
        return None
    hour = _apply_meridiem(int(clock.group("hour")), clock.group("meridiem"))
    minute = int(clock.group("minute"))
    if hour is None or minute >= MINUTES_PER_HOUR:
        return None

    zone = _zone(clock.group("tz"), now)
    reference = now.astimezone(zone) if zone is not None else now
    candidate = reference.replace(hour=hour, minute=minute, second=0, microsecond=0)

    weekday = _WEEKDAY_RE.search(text)
    if weekday is not None:
        target = _WEEKDAYS[weekday.group("weekday").lower()]
        ahead = (target - candidate.weekday()) % DAYS_PER_WEEK
        if ahead == 0 and candidate <= reference:
            ahead = DAYS_PER_WEEK
        candidate += timedelta(days=ahead)
    elif candidate <= reference:
        candidate += timedelta(days=1)

    return candidate.astimezone(now.tzinfo)
