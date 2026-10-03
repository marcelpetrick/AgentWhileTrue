# SPDX-FileCopyrightText: 2026 Marcel Petrick
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Only a visibly empty provider composer counts as a place to type a message."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from agent_while_true import providers
from tests import screens

CURSOR = "\N{HEAVY RIGHT-POINTING ANGLE QUOTATION MARK ORNAMENT}"
CODEX_CURSOR = "\N{SINGLE RIGHT-POINTING ANGLE QUOTATION MARK}"
NOW = datetime(2026, 9, 24, 12, 0, tzinfo=UTC)


def _empty(provider: str, lines: list[str]) -> bool:
    adapter = providers.by_name(provider)
    assert adapter is not None
    return adapter.recognise(lines, now=NOW).composer_empty


@pytest.mark.parametrize(
    ("provider", "lines"),
    [
        ("claude", screens.CLAUDE_IDLE_COMPOSER),
        ("claude", [*screens.CLAUDE_IDLE_COMPOSER, "", ""]),
        ("claude", ["● Done", "─" * 40, CURSOR, "─" * 40]),
        ("codex", screens.CODEX_ACTIVE),
        ("codex", screens.CODEX_IDLE_WITH_FOOTER),
        ("codex", screens.CODEX_USAGE_LIMIT_WITH_PURCHASE_LINKS),
        ("codex", screens.CODEX_USAGE_LIMIT_WITH_PARTICLES),
        ("codex", screens.CODEX_0_158_WORKING),
        ("codex", screens.CODEX_0_158_FOLLOW_UP),
        ("codex", screens.CODEX_0_158_QUEUE_HINT),
        ("codex", screens.CODEX_0_160_WARNING_FOOTER),
        ("codex", screens.CODEX_0_160_PLAN_FOOTER),
    ],
)
def test_empty_composer_is_recognised(provider: str, lines: list[str]) -> None:
    assert _empty(provider, lines)


@pytest.mark.parametrize(
    ("provider", "lines"),
    [
        ("claude", screens.CLAUDE_DRAFT),
        ("claude", screens.CLAUDE_DRAFT_AFTER_NEWLINE),
        # Without the closing rule a continuation row cannot be told from a
        # status line, so an unframed cursor row is not trusted to be empty.
        ("claude", screens.CLAUDE_ACTIVE),
        ("claude", ["● Done", "", CURSOR]),
        ("claude", screens.CLAUDE_LIMIT_MENU),
        ("claude", screens.CLAUDE_SESSION_LIMIT_TYPOGRAPHIC),
        ("claude", ["● Reading a file", "  still working"]),
        ("claude", [f"{CURSOR} ", *[f"  output {n}" for n in range(10)]]),
        ("claude", []),
        ("codex", screens.CODEX_DRAFT),
        ("codex", screens.CODEX_DRAFT_AFTER_NEWLINE),
        ("codex", screens.CODEX_DRAFT_AFTER_NEWLINE_WITH_DOT),
        ("codex", [f"{CODEX_CURSOR} ", "  apples · pears"]),
        ("codex", [f"{CODEX_CURSOR} ", "  first line of a draft", "  gpt-5 high · ~/x · 1% used"]),
        ("codex", ["• Ran cargo test"]),
        # The placeholder's words typed as a longer draft are a draft.
        ("codex", [f"{CODEX_CURSOR} Ask a follow-up question about the parser"]),
        ("codex", [f"{CODEX_CURSOR} ", "  93% of the tests are left"]),
        ("codex", [f"{CODEX_CURSOR} ", "  ? for shortcuts · unfinished draft"]),
    ],
)
def test_draft_menu_or_missing_composer_is_not_empty(provider: str, lines: list[str]) -> None:
    assert not _empty(provider, lines)
