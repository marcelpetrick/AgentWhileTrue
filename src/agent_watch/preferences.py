# SPDX-FileCopyrightText: 2026 Marcel Petrick
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Safe persistence for dashboard presentation preferences.

Preferences are deliberately separate from configuration and supervisor
state.  They can change how the dashboard is displayed, but never what the
supervisor is allowed to do or which session it may operate on.
"""

from __future__ import annotations

import json
import os
import tempfile
from contextlib import suppress
from pathlib import Path
from typing import Any

from agent_watch.tui import HISTORY_LENGTHS, THEMES, DashboardState

PREFERENCES_VERSION = 1
MAX_PREFERENCES_BYTES = 16 * 1024

_PREFERENCE_KEYS = frozenset(
    {
        "version",
        "theme",
        "history_length",
        "show_events",
        "details_visible",
        "help_visible",
    }
)


def _is_bool(value: Any) -> bool:
    return isinstance(value, bool)


def _validated_values(document: Any) -> dict[str, object] | None:
    if not isinstance(document, dict) or set(document) != _PREFERENCE_KEYS:
        return None

    version = document["version"]
    if isinstance(version, bool) or not isinstance(version, int) or version != PREFERENCES_VERSION:
        return None

    theme = document["theme"]
    if not isinstance(theme, str) or theme not in THEMES:
        return None

    history_length = document["history_length"]
    if (
        isinstance(history_length, bool)
        or not isinstance(history_length, int)
        or history_length not in HISTORY_LENGTHS
    ):
        return None

    booleans = {key: document[key] for key in ("show_events", "details_visible", "help_visible")}
    if not all(_is_bool(value) for value in booleans.values()):
        return None
    return {"theme": theme, "history_length": history_length, **booleans}


def load_preferences(path: Path, state: DashboardState) -> None:
    """Load valid presentation preferences into ``state``.

    A missing, oversized, malformed, unsupported, or unreadable file is
    ignored.  Validation completes before any state field is changed.
    """
    try:
        with path.open("rb") as stream:
            payload = stream.read(MAX_PREFERENCES_BYTES + 1)
        if len(payload) > MAX_PREFERENCES_BYTES:
            return
        document = json.loads(payload.decode("utf-8"))
        values = _validated_values(document)
    except (OSError, ValueError, RecursionError):
        return
    if values is None:
        return

    state.theme_index = THEMES.index(values["theme"])
    state.history_index = HISTORY_LENGTHS.index(values["history_length"])
    state.show_events = values["show_events"]
    state.details_visible = values["details_visible"]
    state.help_visible = values["help_visible"]


def save_preferences(path: Path, state: DashboardState) -> bool:
    """Atomically save presentation preferences with owner-only permissions."""
    document = {
        "version": PREFERENCES_VERSION,
        "theme": state.theme,
        "history_length": state.history_length,
        "show_events": state.show_events,
        "details_visible": state.details_visible,
        "help_visible": state.help_visible,
    }
    parent = path.parent
    temporary: str | None = None
    try:
        parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=parent)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(document, stream, sort_keys=True, separators=(",", ":"))
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        Path(temporary).replace(path)
        temporary = None
        return True
    except (OSError, TypeError, ValueError):
        return False
    finally:
        if temporary is not None:
            with suppress(OSError):
                Path(temporary).unlink()


__all__ = ["load_preferences", "save_preferences"]
