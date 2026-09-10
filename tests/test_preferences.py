"""Tests for isolated dashboard preference persistence."""

from __future__ import annotations

import json
from pathlib import Path

from agent_watch.preferences import load_preferences, save_preferences
from agent_watch.tui import DashboardState


def _state_snapshot(state: DashboardState) -> tuple[object, ...]:
    return (
        state.interval_index,
        state.paused,
        state.help_visible,
        state.theme_index,
        state.rescan_requested,
        state.show_events,
        state.history_index,
        state.mode_toggle_requested,
        state.details_visible,
        state.detail_index,
    )


def test_round_trip_only_restores_presentation_fields(tmp_path: Path) -> None:
    path = tmp_path / "preferences.json"
    original = DashboardState.from_interval(3)
    original.theme_index = 3
    original.history_index = 3
    original.show_events = False
    original.details_visible = True
    assert save_preferences(path, original)

    restored = DashboardState.from_interval(60)
    restored.paused = True
    restored.rescan_requested = True
    load_preferences(path, restored)

    assert (restored.theme, restored.history_length) == ("amber", 50)
    assert not restored.show_events
    assert restored.details_visible
    assert not restored.help_visible
    assert restored.interval_index == 8
    assert restored.paused
    assert restored.rescan_requested


def test_missing_or_malformed_preferences_leave_state_unchanged(tmp_path: Path) -> None:
    state = DashboardState.from_interval(2)
    state.theme_index = 2
    state.history_index = 2
    state.show_events = False
    state.details_visible = True
    before = _state_snapshot(state)
    path = tmp_path / "preferences.json"

    load_preferences(path, state)
    assert _state_snapshot(state) == before

    path.write_text('{"version": 2}', encoding="utf-8")
    load_preferences(path, state)
    assert _state_snapshot(state) == before

    path.write_text(
        json.dumps(
            {
                "version": 1,
                "theme": "dark",
                "history_length": True,
                "show_events": True,
                "details_visible": False,
                "help_visible": False,
            }
        ),
        encoding="utf-8",
    )
    load_preferences(path, state)
    assert _state_snapshot(state) == before


def test_schema_is_strict_and_read_is_bounded(tmp_path: Path) -> None:
    path = tmp_path / "preferences.json"
    state = DashboardState.from_interval(2)
    valid = {
        "version": 1,
        "theme": "dark",
        "history_length": 10,
        "show_events": True,
        "details_visible": False,
        "help_visible": False,
    }
    path.write_text(json.dumps({**valid, "unexpected": 1}), encoding="utf-8")
    before = _state_snapshot(state)
    load_preferences(path, state)
    assert _state_snapshot(state) == before

    path.write_bytes(b"{" + b" " * (16 * 1024) + b"}")
    load_preferences(path, state)
    assert _state_snapshot(state) == before


def test_save_uses_owner_only_file_and_excludes_runtime_state(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "preferences.json"
    assert save_preferences(path, DashboardState.from_interval(2))
    assert path.stat().st_mode & 0o777 == 0o600
    document = json.loads(path.read_text(encoding="utf-8"))
    assert set(document) == {
        "version",
        "theme",
        "history_length",
        "show_events",
        "details_visible",
        "help_visible",
    }
    assert "paused" not in document


def test_invalid_encoding_and_deep_json_leave_state_unchanged(tmp_path: Path) -> None:
    path = tmp_path / "preferences.json"
    state = DashboardState.from_interval(2)
    before = _state_snapshot(state)

    path.write_bytes(b"{\xff")
    load_preferences(path, state)
    assert _state_snapshot(state) == before

    path.write_text("[" * 6000 + "]" * 6000, encoding="ascii")
    load_preferences(path, state)
    assert _state_snapshot(state) == before


def test_wrong_boolean_version_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "preferences.json"
    path.write_text(
        json.dumps(
            {
                "version": True,
                "theme": "dark",
                "history_length": 10,
                "show_events": True,
                "details_visible": False,
                "help_visible": False,
            }
        ),
        encoding="utf-8",
    )
    state = DashboardState.from_interval(2)
    before = _state_snapshot(state)
    load_preferences(path, state)
    assert _state_snapshot(state) == before


def test_oversized_integer_uses_defaults_instead_of_crashing(tmp_path: Path) -> None:
    path = tmp_path / "preferences.json"
    path.write_text('{"version":' + "9" * 5000 + "}")
    state = DashboardState.from_interval(2)
    before = _state_snapshot(state)
    load_preferences(path, state)
    assert _state_snapshot(state) == before


def test_replace_failure_preserves_existing_file_and_cleans_temp_files(
    tmp_path: Path, monkeypatch
) -> None:
    path = tmp_path / "preferences.json"
    assert save_preferences(path, DashboardState.from_interval(2))
    original = path.read_bytes()

    def fail_replace(self: Path, target: Path) -> Path:
        raise OSError("simulated replace failure")

    monkeypatch.setattr(Path, "replace", fail_replace)
    assert not save_preferences(path, DashboardState.from_interval(3))
    assert path.read_bytes() == original
    assert list(tmp_path.glob(".preferences.json.*.tmp")) == []
