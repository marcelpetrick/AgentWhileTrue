# SPDX-FileCopyrightText: 2026 Marcel Petrick
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for status rendering."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from agent_watch.config import Config, Mode
from agent_watch.fsm import SupervisedSession
from agent_watch.proc import ProcessIdentity
from agent_watch.quota import Availability, QuotaSnapshot, QuotaWindow
from agent_watch.service_health import HealthState, ProviderHealth
from agent_watch.states import SessionState
from agent_watch.terminal.base import SessionRef
from agent_watch.ui import (
    format_reset,
    format_reset_in,
    render_line,
    render_quota,
    render_status,
)

NOW = datetime(2026, 9, 5, 20, 0, tzinfo=UTC)
REF = SessionRef("konsole", "org.kde.konsole-1", "/Sessions/2")
IDENTITY = ProcessIdentity(pid=15102, start_time=1, tty="pts/3", exe="/opt/claude")


def _session(**overrides) -> SupervisedSession:
    base = {
        "ref": REF,
        "identity": IDENTITY,
        "provider_name": "claude",
        "title": "beta : claude",
        "state": SessionState.WAITING_FOR_RESET,
        "reset_at": NOW + timedelta(hours=1),
    }
    return SupervisedSession(**{**base, **overrides})


def test_status_lists_each_session() -> None:
    text = render_status(
        [_session()],
        now=NOW,
        config=Config(mode=Mode.AUTO),
    )
    assert "WAITING_FOR_RESET" in text
    assert "15102" in text
    assert "mode=auto" in text
    assert "watching 1 session" in text
    assert "QUOTA" in text
    assert "Agent While True" in text
    assert "h help" in text
    assert "ACCOUNT" in text


def test_full_auto_mode_and_toggle_are_explicit_in_dashboard() -> None:
    config = Config(
        mode=Mode.AUTO,
        policy=replace(Config().policy, allow_codex_auto_resume=True),
    )
    text = render_status([_session()], now=NOW, config=config, show_help=True)
    assert "mode=full-auto" in text
    assert "A mode" in text
    assert "toggle observe/full-auto" in text


def test_status_handles_nothing_selected() -> None:
    text = render_status([], now=NOW, config=Config())
    assert "(nothing selected)" in text


def test_reset_beyond_a_day_is_not_shown_as_a_clock_time() -> None:
    # "12:00" for something three days out would be actively misleading.
    assert format_reset(NOW + timedelta(days=3), NOW) == "+3d"
    assert format_reset(NOW + timedelta(days=3, hours=1), NOW) == "+4d"


def test_a_passed_reset_reads_as_due() -> None:
    assert format_reset(NOW - timedelta(minutes=1), NOW) == "due"


def test_no_reset_renders_as_a_dash() -> None:
    assert format_reset(None, NOW) == "-"


@pytest.mark.parametrize(
    ("delta", "expected"),
    [
        (timedelta(minutes=1), "1h"),
        (timedelta(hours=35), "35h"),
        (timedelta(hours=36), "2d"),
        (timedelta(days=3), "3d"),
        (timedelta(seconds=-1), "due"),
    ],
)
def test_compact_reset_countdown(delta: timedelta, expected: str) -> None:
    assert format_reset_in(NOW + delta, NOW) == expected


def test_observe_line_shape() -> None:
    line = render_line(_session(state=SessionState.LIMIT_BLOCKED), NOW)
    assert "claude pts/3: LIMIT_BLOCKED" in line
    assert "until" in line
    assert "quota=UNKNOWN" in line


def test_observe_line_for_an_active_session_has_no_until() -> None:
    line = render_line(_session(state=SessionState.ACTIVE, reset_at=None), NOW)
    assert "ACTIVE" in line
    assert "until" not in line


def test_quota_view_shows_usage_reset_and_errors() -> None:
    snapshot = QuotaSnapshot(
        provider="claude",
        availability=Availability.EXHAUSTED,
        source="statusline",
        observed_at=NOW,
        windows=(QuotaWindow("session", 100.0, NOW + timedelta(hours=1)),),
        note="limit-reached",
    )
    text = render_quota(snapshot, now=NOW, identity="pts/3 PID 12")
    assert "EXHAUSTED" in text
    assert "100.0%" in text
    assert (NOW + timedelta(hours=1)).astimezone().strftime("%H:%M") in text
    assert "(1h)" in text
    assert "limit-reached" in text


def test_dashboard_shows_per_session_account_and_usage_meters() -> None:
    quota = QuotaSnapshot(
        provider="codex",
        availability=Availability.AVAILABLE,
        source="rollout",
        observed_at=NOW,
        windows=(
            QuotaWindow("session", 84.0, NOW + timedelta(hours=1)),
            QuotaWindow("weekly", 77.0, NOW + timedelta(days=3)),
        ),
    )
    session = _session(
        provider_name="codex",
        account_label="codex-dmo · work@example.com",
        quota=quota,
    )

    text = render_status([session], now=NOW, config=Config())

    assert "codex-dmo · work@example.com" in text
    assert "84%" in text
    assert "77%" in text
    assert "/16" not in text
    assert "/23" not in text
    assert "[████░]" in text
    assert "84% 1h" in text
    assert "77% 3d" in text


def test_dashboard_shows_cached_service_health() -> None:
    health = {
        "openai": ProviderHealth("openai", HealthState.ONLINE, "ok", NOW),
        "anthropic": ProviderHealth("anthropic", HealthState.DEGRADED, "incident", NOW),
    }
    text = render_status(
        [_session()],
        now=NOW + timedelta(seconds=1),
        config=Config(),
        service_health=health,
    )
    assert "OpenAI: ONLINE (1s ago)" in text
    assert "Anthropic: DEGRADED" in text
    assert "incident" in text


def test_dashboard_explains_service_errors_and_refuses_stale_online_state() -> None:
    health = {
        "openai": ProviderHealth("openai", HealthState.ONLINE, "ok", NOW),
        "anthropic": ProviderHealth(
            "anthropic", HealthState.DEGRADED, "Claude Code=degraded_performance", NOW
        ),
    }
    text = render_status(
        [],
        now=NOW + timedelta(minutes=3),
        config=Config(status_poll_interval=60),
        service_health=health,
    )
    assert "OpenAI: UNKNOWN (180s ago; stale-status)" in text
    assert "Anthropic: UNKNOWN (180s ago; stale-status)" in text


def test_colored_dashboard_and_help_are_optional() -> None:
    plain = render_status([_session()], now=NOW, config=Config(), show_help=True)
    colored = render_status(
        [_session()], now=NOW, config=Config(), show_help=True, color=True, theme="vivid"
    )
    assert "\x1b[" not in plain
    assert "refresh faster / slower" in plain
    assert "\x1b[" in colored
    assert "\x1b[38;5;231;48;5;17m" in colored
    assert "│" in colored
    assert "└" in colored


def test_cga_and_amber_themes_use_distinct_palettes() -> None:
    cga = render_status([_session()], now=NOW, config=Config(), color=True, theme="cga")
    amber = render_status([_session()], now=NOW, config=Config(), color=True, theme="amber")
    assert "\x1b[1;96;40m" in cga
    assert "\x1b[1;38;5;214;48;5;52m" in amber
    assert cga != amber


def test_every_theme_renders_a_complete_fixed_width_panel() -> None:
    ansi = re.compile(r"\x1b\[[0-9;]*m")
    for theme in ("dark", "vivid", "cga", "amber", "plain"):
        text = render_status(
            [_session()], now=NOW, config=Config(), color=theme != "plain", theme=theme
        )
        assert all(len(ansi.sub("", line)) == 168 for line in text.splitlines())


def test_reset_headings_explain_their_values() -> None:
    text = render_status([_session()], now=NOW, config=Config())
    assert "PROMPT RESET" in text
    assert "QUOTA RESET" in text


def test_codex_node_launcher_is_presented_as_codex() -> None:
    session = _session(provider_name="codex", title="AgentWhileTrue : node")
    text = render_status([session], now=NOW, config=Config())
    assert "AgentWhileTrue : Codex" in text
    assert "AgentWhileTrue : node" not in text


def test_dashboard_can_show_persisted_history() -> None:
    text = render_status(
        [_session()],
        now=NOW,
        config=Config(),
        events=["event=state_change session=/Sessions/2 state=LIMIT_BLOCKED"],
        history_length=10,
    )
    assert "HISTORY (last 10)" in text
    assert "event=state_change" in text


def test_dashboard_renders_only_selected_rows_from_retained_history() -> None:
    events = [f"event=resume_sent attempt={number}" for number in range(50)]
    text = render_status([_session()], now=NOW, config=Config(), events=events, history_length=5)
    assert "HISTORY (last 5)" in text
    assert "attempt=44" not in text
    assert "attempt=45" in text
    assert "attempt=49" in text


def test_details_show_missing_and_stale_evidence_without_permission() -> None:
    session = _session(last_reason="quota-stale", observed_at=NOW - timedelta(minutes=20))
    text = render_status([session], now=NOW, config=Config(), show_details=True, paused=True)
    assert "quota-stale" in text
    assert "STALE" in text
    assert "not observed" in text
    assert "Next check: paused" in text
    assert "continuation is not guaranteed" in text


def test_detail_selection_wraps_and_reports_exhausted_windows() -> None:
    quota = QuotaSnapshot(
        "claude",
        Availability.EXHAUSTED,
        "statusline",
        NOW,
        (QuotaWindow("weekly", 100, NOW + timedelta(days=1)),),
    )
    session = _session(quota=quota, last_reason="weekly-exhausted")
    text = render_status(
        [_session(), session], now=NOW, config=Config(), show_details=True, detail_index=-1
    )
    assert "DETAIL 2/2" in text
    assert "weekly-exhausted" in text
    assert "Exhausted windows (last sample): weekly" in text


@pytest.mark.parametrize("width", [80, 120, 168, 200])
def test_dashboard_respects_explicit_widths(width: int) -> None:
    text = render_status([_session()], now=NOW, config=Config(), width=width)
    assert all(len(line) == width for line in text.splitlines())
    if width < 168:
        assert "ACCOUNT:" in text
        assert "SESSION:" in text
        assert "TYPE:" in text
    else:
        assert "ACCOUNT" in text
        assert "PROMPT RESET" in text


@pytest.mark.parametrize("theme", ["dark", "vivid", "cga", "amber", "plain"])
def test_narrow_dashboard_supports_every_theme(theme: str) -> None:
    text = render_status(
        [_session()], now=NOW, config=Config(), width=80, color=theme != "plain", theme=theme
    )
    assert "SESSION 1/1" in text
    if theme != "plain":
        assert "\x1b[" in text


def test_narrow_dashboard_wraps_unicode_and_strips_terminal_controls() -> None:
    session = _session(title="very-long-日本語-\x1b[31m-title-" + "x" * 100)
    text = render_status([session], now=NOW, config=Config(), width=40)
    assert "\x1b[31m" not in text
    assert "日本語" in text
    assert all(_display_width(line) == 40 for line in text.splitlines())


def test_small_viewport_keeps_navigation_and_reaches_history_end() -> None:
    events = [f"event=resume_sent attempt={number}" for number in range(12)]
    text = render_status(
        [_session()],
        now=NOW,
        config=Config(),
        width=80,
        height=6,
        scroll_offset=10**9,
        events=events,
        history_length=10,
        show_help=False,
    )
    assert len(text.splitlines()) == 6
    assert "j/k scroll" in text
    assert "└" in text
    assert "attempt=11" in text


def _display_width(line: str) -> int:
    plain = re.sub(r"\x1b\[[0-9;]*m", "", line)
    return sum(
        0 if unicodedata.combining(char) else 2 if unicodedata.east_asian_width(char) in "WF" else 1
        for char in plain
    )


@pytest.mark.parametrize("width", [1, 2, 4, 5, 20, 40, 80, 120, 168, 200])
@pytest.mark.parametrize("height", [1, 2, 3, 4, 12])
def test_small_colored_viewports_never_overflow(width: int, height: int) -> None:
    text = render_status(
        [_session(title="日本語 é " * 20)],
        now=NOW,
        config=Config(),
        width=width,
        height=height,
        color=True,
        show_details=True,
        show_help=True,
    )
    assert len(text.splitlines()) <= height
    assert all(_display_width(line) == width for line in text.splitlines())


def test_scrolling_makes_every_body_line_accessible() -> None:
    from agent_watch.ui import render_viewport

    frame = render_status(
        [_session()],
        now=NOW,
        config=Config(),
        width=40,
        show_details=True,
        show_help=True,
        events=["last history entry with a long payload " * 3],
    )
    seen = set()
    for offset in range(len(frame.splitlines())):
        page = render_viewport(frame, 6, offset)
        assert "j/k g/G h q" in page
        seen.update(page.splitlines())
    assert set(frame.splitlines()) <= seen


def test_end_jump_can_scroll_back_and_resize_clamps_offset() -> None:
    from agent_watch.tui import DashboardState
    from agent_watch.ui import clamp_scroll_offset

    state = DashboardState.from_interval(2)
    state.handle("G")
    state.scroll_offset = clamp_scroll_offset(100, 20, state.scroll_offset)
    assert state.scroll_offset == 80
    state.handle("k")
    assert state.scroll_offset == 79
    state.scroll_offset = clamp_scroll_offset(10, 20, state.scroll_offset)
    assert state.scroll_offset == 0
