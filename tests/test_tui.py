"""Tests for interactive dashboard state without touching a real terminal."""

from agent_watch.tui import INTERVALS, THEMES, DashboardState


def test_refresh_keys_follow_btop_interval_direction() -> None:
    state = DashboardState.from_interval(2)
    state.handle("+")
    assert state.interval == 3
    state.handle("-")
    assert state.interval == 2


def test_dashboard_keys_toggle_state_and_quit() -> None:
    state = DashboardState.from_interval(1)
    assert not state.handle("p")
    assert state.paused
    state.handle("h")
    assert state.help_visible
    state.handle("r")
    assert state.rescan_requested
    state.handle("t")
    assert state.theme == "vivid"
    state.handle("e")
    assert not state.show_events
    state.handle("l")
    assert state.history_length == 20
    state.handle("a")
    assert not state.consume_mode_toggle()
    state.handle("A")
    assert state.consume_mode_toggle()
    assert not state.consume_mode_toggle()
    assert state.handle("q")


def test_detail_controls_do_not_toggle_input_mode() -> None:
    state = DashboardState.from_interval(2)
    state.handle("d")
    state.handle("]")
    assert state.details_visible
    assert state.detail_index == 1
    state.handle("[")
    assert state.detail_index == 0
    assert not state.consume_mode_toggle()


def test_refresh_ladder_clamps_at_both_ends() -> None:
    state = DashboardState.from_interval(INTERVALS[0])
    state.handle("-")
    assert state.interval == INTERVALS[0]
    state.interval_index = len(INTERVALS) - 1
    state.handle("+")
    assert state.interval == INTERVALS[-1]


def test_dashboard_cycles_all_five_themes() -> None:
    state = DashboardState.from_interval(2)
    visited = [state.theme]
    for _ in range(len(THEMES) - 1):
        state.handle("t")
        visited.append(state.theme)
    assert visited == ["dark", "vivid", "cga", "amber", "plain"]
    state.handle("t")
    assert state.theme == "dark"
