"""Rendering for the running watcher.

Plain text, no curses. Optional ANSI styling is applied as complete themed
panels, while plain output stays pipe-able, greppable and readable in tests.
"""

from __future__ import annotations

import math
import re
import unicodedata
from collections.abc import Iterable, Sequence
from datetime import datetime

from agent_watch.config import Config, Mode
from agent_watch.fsm import SupervisedSession
from agent_watch.quota import Availability, QuotaSnapshot
from agent_watch.service_health import HealthState, ProviderHealth
from agent_watch.states import SessionState
from agent_watch.version import __version__

CLEAR_SCREEN = "\x1b[H\x1b[2J"
HIDE_CURSOR = "\x1b[?25l"
SHOW_CURSOR = "\x1b[?25h"

_DARK = {
    "surface": "\x1b[38;5;252;48;5;235m",
    "structure": "\x1b[1;38;5;45;48;5;235m",
    "header": "\x1b[1;38;5;16;48;5;45m",
    "text": "\x1b[38;5;252;48;5;235m",
    "accent": "\x1b[1;38;5;51;48;5;235m",
    "healthy": "\x1b[1;38;5;48;48;5;235m",
    "warning": "\x1b[1;38;5;220;48;5;235m",
    "danger": "\x1b[1;38;5;203;48;5;235m",
    "claude": "\x1b[1;38;5;213;48;5;235m",
    "codex": "\x1b[1;38;5;75;48;5;235m",
    "dim": "\x1b[38;5;245;48;5;235m",
}
_VIVID = {
    "surface": "\x1b[38;5;231;48;5;17m",
    "structure": "\x1b[1;38;5;51;48;5;17m",
    "header": "\x1b[1;38;5;16;48;5;201m",
    "text": "\x1b[38;5;231;48;5;17m",
    "accent": "\x1b[1;38;5;226;48;5;17m",
    "healthy": "\x1b[1;38;5;48;48;5;17m",
    "warning": "\x1b[1;38;5;214;48;5;17m",
    "danger": "\x1b[1;38;5;196;48;5;17m",
    "claude": "\x1b[1;38;5;213;48;5;17m",
    "codex": "\x1b[1;38;5;81;48;5;17m",
    "dim": "\x1b[38;5;153;48;5;17m",
}
_CGA = {
    "surface": "\x1b[37;40m",
    "structure": "\x1b[1;96;40m",
    "header": "\x1b[1;97;45m",
    "text": "\x1b[97;40m",
    "accent": "\x1b[1;95;40m",
    "healthy": "\x1b[1;96;40m",
    "warning": "\x1b[1;97;44m",
    "danger": "\x1b[1;97;45m",
    "claude": "\x1b[1;95;40m",
    "codex": "\x1b[1;96;40m",
    "dim": "\x1b[37;40m",
}
_AMBER = {
    "surface": "\x1b[38;5;223;48;5;52m",
    "structure": "\x1b[1;38;5;214;48;5;52m",
    "header": "\x1b[1;38;5;52;48;5;214m",
    "text": "\x1b[38;5;223;48;5;52m",
    "accent": "\x1b[1;38;5;228;48;5;52m",
    "healthy": "\x1b[1;38;5;220;48;5;52m",
    "warning": "\x1b[1;38;5;208;48;5;52m",
    "danger": "\x1b[1;38;5;196;48;5;52m",
    "claude": "\x1b[1;38;5;215;48;5;52m",
    "codex": "\x1b[1;38;5;221;48;5;52m",
    "dim": "\x1b[38;5;172;48;5;52m",
}
_PALETTES = {"dark": _DARK, "vivid": _VIVID, "cga": _CGA, "amber": _AMBER}
_RESET = "\x1b[0m"

_HEADERS = (
    "ID",
    "TYPE",
    "ACCOUNT",
    "STATE",
    "PROMPT RESET",
    "5H USED/IN",
    "WEEK USED/IN",
    "QUOTA",
    "QUOTA RESET",
    "PID",
    "SESSION",
)
_WIDTHS = (3, 7, 31, 18, 12, 16, 16, 10, 12, 7, 0)
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f-\x9f]")
_ESCAPE_RE = re.compile(r"\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)|\x1b\[[0-?]*[ -/]*[@-~]")


def _safe_text(value: object) -> str:
    """Remove terminal controls before text reaches an ANSI themed panel."""
    return _CONTROL_RE.sub("", _ESCAPE_RE.sub("", str(value)))


def _cell_width(value: str) -> int:
    return sum(
        0 if unicodedata.combining(char) else 2 if unicodedata.east_asian_width(char) in "WF" else 1
        for char in value
    )


def _fit(value: object, width: int) -> str:
    text = _safe_text(value)
    if width <= 0:
        return ""
    result: list[str] = []
    used = 0
    for char in text:
        char_width = (
            0
            if unicodedata.combining(char)
            else 2
            if unicodedata.east_asian_width(char) in "WF"
            else 1
        )
        if used + char_width > width:
            break
        result.append(char)
        used += char_width
    return "".join(result) + " " * (width - used)


def _wrap(value: object, width: int) -> list[str]:
    """Wrap in one pass, including fields wider than the complete terminal."""
    text = _safe_text(value)
    if width <= 0:
        return [""]
    if not text:
        return [""]
    lines: list[str] = []
    chars: list[str] = []
    used = 0
    for char in text:
        cells = _cell_width(char)
        if cells > width:
            char, cells = "?", 1
        if used + cells > width:
            lines.append("".join(chars))
            chars, used = [], 0
        chars.append(char)
        used += cells
    if chars:
        lines.append("".join(chars))
    return lines


def format_reset(reset_at: datetime | None, now: datetime) -> str:
    """Render a reset instant as a local wall-clock time, or a relative hint.

    Beyond a day out, a bare clock time is misleading, so the day count is
    shown instead.
    """
    if reset_at is None:
        return "-"
    seconds = (reset_at - now).total_seconds()
    if seconds < 0:
        return "due"
    if seconds >= 24 * 60 * 60:
        return f"+{math.ceil(seconds / (24 * 60 * 60))}d"
    return reset_at.astimezone().strftime("%H:%M")


def format_reset_in(reset_at: datetime | None, now: datetime) -> str:
    """Render a compact conservative countdown in hours or days."""
    if reset_at is None:
        return "-"
    seconds = (reset_at - now).total_seconds()
    if seconds <= 0:
        return "due"
    if seconds < 1.5 * 24 * 60 * 60:
        return f"{math.ceil(seconds / (60 * 60))}h"
    return f"{math.ceil(seconds / (24 * 60 * 60))}d"


def _row(values: Sequence[str]) -> str:
    parts = []
    for value, width in zip(values, _WIDTHS, strict=True):
        parts.append(_safe_text(value) if width == 0 else _fit(value, width))
    return " ".join(parts).rstrip()


def _paint(text: str, role: str, *, color: bool, theme: str) -> str:
    if not color or theme == "plain":
        return text
    palette = _PALETTES.get(theme, _DARK)
    return f"{palette[role]}{text}{_RESET}"


def _panel_line(text: str, width: int, role: str, *, color: bool, theme: str) -> str:
    """Pad and frame one line so the theme covers the complete panel."""
    if width < 5:
        return _paint(_fit(text, width), role, color=color, theme=theme)
    inner = max(1, width - 4)
    content = _fit(text, inner)
    plain = f"│ {content} │"
    return _paint(plain, role, color=color, theme=theme)


def _styled_row(
    values: Sequence[str], roles: Sequence[str], width: int, *, color: bool, theme: str
) -> str:
    """Render semantic cells on the theme surface inside a panel border."""
    if not color or theme == "plain":
        return _panel_line(_row(values), width, "surface", color=False, theme=theme)
    cells = []
    fixed_width = sum(_WIDTHS[:-1]) + len(_WIDTHS) - 1
    final_width = max(1, width - fixed_width - 4)
    for index, (value, cell_width, role) in enumerate(zip(values, _WIDTHS, roles, strict=True)):
        target_width = final_width if index == len(_WIDTHS) - 1 else cell_width
        content = _fit(value, target_width)
        cells.append(_paint(content, role, color=True, theme=theme))
        if index != len(_WIDTHS) - 1:
            cells.append(_paint(" ", "surface", color=True, theme=theme))
    border = _paint("│ ", "structure", color=True, theme=theme)
    return border + "".join(cells) + _paint(" │", "structure", color=True, theme=theme)


def _rule(title: str, width: int, *, color: bool, theme: str) -> str:
    prefix = f"┌─ {title} "
    prefix = _safe_text(prefix)
    plain = prefix + "─" * max(1, width - _cell_width(prefix) - 1) + "┐"
    plain = _fit(plain, width)
    return _paint(plain, "structure", color=color, theme=theme)


def _state_role(value: str) -> str:
    if value in {"ACTIVE", "AVAILABLE", "READY_TO_RESUME", "ONLINE"}:
        return "healthy"
    if value in {"UNSAFE", "PROCESS_GONE", "EXHAUSTED", "OUTAGE"}:
        return "danger"
    return "warning"


def _usage_role(snapshot: QuotaSnapshot, scope: str) -> str:
    window = next((item for item in snapshot.windows if item.scope == scope), None)
    if window is None:
        return "dim"
    if window.used_percent >= 100:
        return "danger"
    if window.used_percent >= 75:
        return "warning"
    return "healthy"


def quota_state(snapshot: QuotaSnapshot, now: datetime) -> str:
    """Render availability without presenting stale data as authoritative."""
    if snapshot.availability is not Availability.UNKNOWN and snapshot.is_stale(now):
        return "STALE"
    return snapshot.availability.value


def quota_meter(snapshot: QuotaSnapshot, scope: str) -> str:
    """Render a compact btop-style meter containing only used percentage."""
    window = next((item for item in snapshot.windows if item.scope == scope), None)
    if window is None:
        return "-"
    used = max(0, min(100, round(window.used_percent)))
    filled = min(5, round(used / 20))
    return f"[{'█' * filled}{'░' * (5 - filled)}] {used:>3}%"


def quota_meter_with_reset(snapshot: QuotaSnapshot, scope: str, now: datetime) -> str:
    """Combine one quota meter with its own compact reset countdown."""
    window = next((item for item in snapshot.windows if item.scope == scope), None)
    if window is None:
        return "-"
    return f"{quota_meter(snapshot, scope)} {format_reset_in(window.resets_at, now)}"


def _health_age(health: ProviderHealth, now: datetime) -> str:
    if health.checked_at is None:
        return "never"
    seconds = max(0, round((now - health.checked_at).total_seconds()))
    return f"{seconds}s ago"


def _health_text(health: ProviderHealth, now: datetime, max_age: float) -> str:
    state = health.state
    detail = health.detail
    if health.checked_at is not None and (now - health.checked_at).total_seconds() > max_age:
        state = HealthState.UNKNOWN
        detail = "stale-status"
    suffix = f"; {detail}" if state is not HealthState.ONLINE and detail else ""
    return f"{state.value} ({_health_age(health, now)}{suffix})"


def render_quota(snapshot: QuotaSnapshot, *, now: datetime, identity: str = "") -> str:
    """Render a provider snapshot for the ``quota`` query command."""
    lines = [
        f"{snapshot.provider.title()} {identity}".rstrip(),
        f"  availability: {quota_state(snapshot, now)}",
        f"  source:       {snapshot.source}",
    ]
    if snapshot.note:
        lines.append(f"  detail:       {snapshot.note}")
    if not snapshot.windows:
        lines.append("  windows:      no usable data")
    for window in snapshot.windows:
        reset = format_reset(window.resets_at, now)
        reset_in = format_reset_in(window.resets_at, now)
        lines.append(
            f"  {window.scope:<12} {window.used_percent:>6.1f}%  reset {reset} ({reset_in})"
        )
    return "\n".join(lines)


def session_details(
    session: SupervisedSession, now: datetime, interval: float, paused: bool = False
) -> list[str]:
    """Explain cached evidence without evaluating policy or reading a terminal."""

    def age(moment: datetime | None) -> str:
        if moment is None:
            return "not observed"
        seconds = (now - moment).total_seconds()
        return "clock changed; recheck required" if seconds < 0 else f"{seconds:.0f}s ago"

    observation_age = (now - session.observed_at).total_seconds() if session.observed_at else None
    stale = observation_age is None or observation_age < 0 or observation_age > interval * 2
    scheduled = session.verify_after or session.next_check_at
    next_check = (
        scheduled.astimezone().isoformat(timespec="seconds")
        if scheduled
        else f"next scan (every {interval:g}s)"
    )
    return [
        f"Session: {session.provider_name} {session.identity.tty} PID {session.identity.pid}",
        f"Title: {session.display_title()}",
        f"Account: {session.account_label}",
        f"Last decision: {session.last_reason or 'not evaluated'} ({age(session.decision_at)})",
        f"Observation: {age(session.observed_at)}{'; STALE' if stale else ''}",
        f"Recognized state: {session.observed_state}",
        f"Patterns: {', '.join(session.matched_ids) or 'none'}",
        f"Quota: {quota_state(session.quota, now)}; source={session.quota.source}; "
        f"age={age(session.quota.observed_at)}",
        f"Quota detail: {session.quota.note or 'none'}",
        "Exhausted windows (last sample): "
        + (", ".join(sorted(session.quota.exhausted_scopes)) or "none reported"),
        f"Next check: {'paused' if paused else next_check}; continuation is not guaranteed",
        "Cached evidence only; every action requires fresh policy and identity checks.",
    ]


def _session_card(
    session: SupervisedSession,
    index: int,
    total: int,
    now: datetime,
    panel_width: int,
    *,
    color: bool,
    theme: str,
) -> list[str]:
    quota_value = quota_state(session.quota, now)
    fields = (
        ("ID", str(index)),
        ("TYPE", session.provider_name.title()),
        ("ACCOUNT", session.account_label),
        ("STATE", session.state.value),
        ("PROMPT RESET", format_reset(session.reset_at, now)),
        ("5H USED/IN", quota_meter_with_reset(session.quota, "session", now)),
        ("WEEK USED/IN", quota_meter_with_reset(session.quota, "weekly", now)),
        ("QUOTA", quota_value),
        ("QUOTA RESET", format_reset(session.quota.next_reset, now)),
        ("PID", str(session.identity.pid)),
        ("SESSION", session.display_title()),
    )
    lines = [
        _panel_line(f"SESSION {index}/{total}", panel_width, "header", color=color, theme=theme)
    ]
    inner = max(1, panel_width - 4)
    for label, value in fields:
        for part in _wrap(f"{label}: {value}", inner):
            lines.append(_panel_line(part, panel_width, "text", color=color, theme=theme))
    return lines


def clamp_scroll_offset(line_count: int, height: int | None, offset: int) -> int:
    """Normalize stored navigation after end-of-page jumps or a resize."""
    if height is None or line_count <= height:
        return 0
    return min(max(0, offset), max(0, line_count - max(3, height)))


def render_viewport(text: str, height: int | None, offset: int) -> str:
    return _viewport(text.splitlines(), height, offset)


def _viewport(lines: list[str], height: int | None, offset: int) -> str:
    if height is None:
        return "\n".join(lines)
    if height <= 0 or not lines:
        return ""
    if height == 1:
        return lines[-1]
    if height == 2:
        return "\n".join((lines[0], lines[-1]))
    header = lines[:2] if height >= 4 else lines[:1]
    footer = lines[-1]
    body = lines[len(header) : -1]
    visible = height - len(header) - 1
    start = clamp_scroll_offset(len(lines), height, offset)
    return "\n".join([*header, *body[start : start + visible], footer])


def render_status(
    sessions: Iterable[SupervisedSession],
    *,
    now: datetime,
    config: Config,
    last_event: str = "",
    refresh_interval: float | None = None,
    paused: bool = False,
    show_help: bool = False,
    color: bool = False,
    theme: str = "dark",
    width: int = 168,
    height: int | None = None,
    scroll_offset: int = 0,
    events: Sequence[str] = (),
    show_events: bool = True,
    history_length: int = 10,
    show_details: bool = False,
    detail_index: int = 0,
    service_health: dict[str, ProviderHealth] | None = None,
) -> str:
    """Render the running watcher's status table."""
    listed = list(sessions)
    title = f"Agent While True {__version__}"
    panel_width = max(1, width)
    interval = refresh_interval if refresh_interval is not None else config.scan_interval
    pause_badge = " — PAUSED: press p to resume" if paused else ""
    mode_label = (
        "full-auto"
        if config.mode is Mode.AUTO and config.policy.allow_codex_auto_resume
        else config.mode.value
    )
    lines = [
        _rule(title + pause_badge, panel_width, color=color, theme=theme),
        _panel_line(
            f"mode={mode_label}   watching {len(listed)} session(s)   theme={theme}   "
            f"every {interval:g}s{'   PAUSED' if paused else ''}",
            panel_width,
            "accent",
            color=color,
            theme=theme,
        ),
    ]
    for part in _wrap(
        f"{now.astimezone().strftime('%Y-%m-%d %H:%M:%S')}  "
        "+ slower  - faster  A mode  e events  l history  r rescan  p pause  t theme  d details",
        max(1, panel_width - 4),
    ):
        lines.append(_panel_line(part, panel_width, "surface", color=color, theme=theme))
    if service_health:
        status_parts = []
        health_roles = []
        health_max_age = max(10.0, config.status_poll_interval * 2)
        for provider, label in (("openai", "OpenAI"), ("anthropic", "Anthropic")):
            health = service_health.get(provider, ProviderHealth(provider, HealthState.UNKNOWN, ""))
            status_parts.append(f"{label}: {_health_text(health, now, health_max_age)}")
            health_roles.append(_state_role(health.state.value))
        service_role = (
            "danger"
            if "danger" in health_roles
            else ("warning" if "warning" in health_roles else "healthy")
        )
        lines.extend(
            _panel_line(
                part,
                panel_width,
                service_role,
                color=color,
                theme=theme,
            )
            for part in _wrap("services=" + "   ".join(status_parts), max(1, panel_width - 4))
        )
    lines.extend(
        (
            _panel_line("", panel_width, "surface", color=color, theme=theme),
            _panel_line("SESSIONS", panel_width, "header", color=color, theme=theme),
        )
    )
    if panel_width < 168:
        for index, session in enumerate(listed, start=1):
            lines.extend(
                _session_card(
                    session,
                    index,
                    len(listed),
                    now,
                    panel_width,
                    color=color,
                    theme=theme,
                )
            )
    if panel_width >= 168:
        lines.extend(
            (
                _styled_row(
                    _HEADERS,
                    ("header",) * len(_HEADERS),
                    panel_width,
                    color=color,
                    theme=theme,
                ),
                _panel_line(
                    "─" * (panel_width - 4),
                    panel_width,
                    "structure",
                    color=color,
                    theme=theme,
                ),
            )
        )
    for index, session in enumerate(listed, start=1):
        if panel_width < 168:
            break
        quota_value = quota_state(session.quota, now)
        values = (
            str(index),
            session.provider_name.title(),
            session.account_label,
            session.state.value,
            format_reset(session.reset_at, now),
            quota_meter_with_reset(session.quota, "session", now),
            quota_meter_with_reset(session.quota, "weekly", now),
            quota_value,
            format_reset(session.quota.next_reset, now),
            str(session.identity.pid),
            session.display_title(),
        )
        roles = (
            "accent",
            session.provider_name if session.provider_name in {"codex", "claude"} else "text",
            "text",
            _state_role(session.state.value),
            "warning" if session.reset_at else "dim",
            _usage_role(session.quota, "session"),
            _usage_role(session.quota, "weekly"),
            _state_role(quota_value),
            "warning" if session.quota.next_reset else "dim",
            "dim",
            "text",
        )
        lines.append(_styled_row(values, roles, panel_width, color=color, theme=theme))
    if not listed:
        lines.append(
            _panel_line("(nothing selected)", panel_width, "dim", color=color, theme=theme)
        )
    lines.append(_panel_line("", panel_width, "surface", color=color, theme=theme))
    if show_details and listed:
        selected = detail_index % len(listed)
        lines.append(
            _panel_line(
                f"DETAIL {selected + 1}/{len(listed)} ([ / ] select; d hide)",
                panel_width,
                "header",
                color=color,
                theme=theme,
            )
        )
        for detail in session_details(listed[selected], now, interval, paused):
            lines.extend(
                _panel_line(part, panel_width, "text", color=color, theme=theme)
                for part in _wrap(detail, max(1, panel_width - 4))
            )
    if last_event:
        lines.extend(
            _panel_line(part, panel_width, "accent", color=color, theme=theme)
            for part in _wrap(f"Last: {last_event}", max(1, panel_width - 4))
        )
    if show_events and events:
        lines.append(_panel_line("", panel_width, "surface", color=color, theme=theme))
        lines.append(
            _panel_line(
                f"HISTORY (last {history_length})",
                panel_width,
                "header",
                color=color,
                theme=theme,
            )
        )
        for event in events[-history_length:]:
            lines.extend(
                _panel_line(part, panel_width, "dim", color=color, theme=theme)
                for part in _wrap(event, max(1, panel_width - 4))
            )
    if show_help:
        lines.extend(
            (
                _panel_line("", panel_width, "surface", color=color, theme=theme),
                _panel_line("KEYS", panel_width, "header", color=color, theme=theme),
                *(
                    _panel_line(part, panel_width, "text", color=color, theme=theme)
                    for item in (
                        "- / +   refresh faster / slower (0.25, 0.5, 1, 2, 3, 5, 10, 30, 60s)",
                        "A       toggle observe/full-auto; full-auto opts in Codex continuation",
                        "p       pause/resume; paused means no terminal or quota polling",
                        "r       rediscover Konsole sessions now",
                        "t       cycle dark, vivid, CGA, amber and plain themes",
                        "e       show/hide persisted action history",
                        "l       cycle history length: 5, 10, 20, 50",
                        "d       show/hide resume explanation; [ / ] previous/next session",
                        "j / k   scroll down/up; g / G jump to top/end",
                        "h / ?   close this help",
                        "q       quit cleanly",
                    )
                    for part in _wrap(item, max(1, panel_width - 4))
                ),
            )
        )
    hint = "j/k scroll  g/G top/end  h help  q quit"
    if panel_width < 44:
        hint = "j/k g/G h q"
    bottom = "└ " + _fit(hint, max(0, panel_width - 4)) + " ┘"
    lines.append(_paint(_fit(bottom, panel_width), "structure", color=color, theme=theme))
    return _viewport(lines, height, scroll_offset)


def render_line(session: SupervisedSession, now: datetime) -> str:
    """One-line observe-mode output, in the shape the vision sketches."""
    stamp = now.astimezone().strftime("%H:%M:%S")
    suffix = ""
    if session.state in {SessionState.LIMIT_BLOCKED, SessionState.WAITING_FOR_RESET}:
        suffix = f" until {format_reset(session.reset_at, now)}"
    return (
        f"[{stamp}] {session.provider_name} {session.identity.tty}: {session.state.value}{suffix}"
        f" quota={quota_state(session.quota, now)}"
        f" quota_reset={format_reset(session.quota.next_reset, now)}"
    )
