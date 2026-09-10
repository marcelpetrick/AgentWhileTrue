# SPDX-FileCopyrightText: 2026 Marcel Petrick
# SPDX-License-Identifier: GPL-3.0-or-later
"""Operation-count regressions for hot display-width paths."""

from __future__ import annotations

from agent_watch import ui


def test_ascii_fit_and_wrap_skip_unicode_database(monkeypatch) -> None:
    calls = 0

    def counted(_: str) -> int:
        nonlocal calls
        calls += 1
        return 0

    monkeypatch.setattr(ui.unicodedata, "combining", counted)
    monkeypatch.setattr(ui.unicodedata, "east_asian_width", lambda char: counted(char) or "Na")

    assert ui._fit("plain dashboard text", 10) == "plain dash"
    assert ui._wrap("abcdefghijkl", 5) == ["abcde", "fghij", "kl"]
    assert ui._cell_width("plain dashboard text") == 20
    assert calls == 0


def test_unicode_width_paths_preserve_wide_and_combining_semantics() -> None:
    value = "A界e\N{COMBINING ACUTE ACCENT}Z"
    assert ui._cell_width(value) == 5
    assert ui._fit(value, 4) == "A界e\N{COMBINING ACUTE ACCENT}"
    assert ui._wrap(value, 3) == ["A界", "e\N{COMBINING ACUTE ACCENT}Z"]
