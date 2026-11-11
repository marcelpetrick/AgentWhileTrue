# SPDX-FileCopyrightText: 2026 Marcel Petrick
# SPDX-License-Identifier: GPL-3.0-or-later
"""Regressions for the 2026-11-11 overnight Codex CLI 0.167.0 limit.

The exact limit composer stayed on screen after its 2:48 AM reset and no
continuation was typed: the dated reset, the recap block and the extended status
row each made the screen fail the exact-composer gate.
"""

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from agent_while_true import providers
from agent_while_true.config import Config, Mode, Policy
from agent_while_true.quota import Availability
from agent_while_true.states import SessionState
from tests import screens
from tests.harness import build

GLYPH = "\N{SINGLE RIGHT-POINTING ANGLE QUOTATION MARK}"
BERLIN = ZoneInfo("Europe/Berlin")
#: When the limit banner was first observed.
SEEN = datetime(2026, 11, 10, 22, 52, 11, tzinfo=BERLIN)
RESET = datetime(2026, 11, 11, 2, 48, tzinfo=BERLIN)
SCREEN = screens.CODEX_0_167_LIMIT_WITH_RECAP
RECAP_START = next(i for i, line in enumerate(SCREEN) if "↳ Recap:" in line)


def test_live_0_167_limit_is_the_exact_retry_prompt() -> None:
    result = providers.CODEX.recognise(SCREEN, now=SEEN)

    assert result.state is SessionState.LIMIT_BLOCKED
    assert result.retry_prompt
    assert result.composer_empty
    assert result.input_ready
    assert result.reset_at == RESET
    assert result.action is not None
    assert result.action.text == "continue"
    assert {"codex/limit-usage", "codex/try-again-at"}.issubset(result.matched_ids)


def test_dated_banner_without_recap_is_exact() -> None:
    # Without a recap Codex leaves one blank row between banner and composer.
    screen = [*SCREEN[:RECAP_START], *SCREEN[RECAP_START + 7 :]]
    result = providers.CODEX.recognise(screen, now=SEEN)

    assert result.retry_prompt
    assert result.reset_at == RESET


@pytest.mark.parametrize(
    "recap",
    [
        "  ↳ Recap: Visit the page to purchase more credits before continuing.",
        "  ↳ Recap: Keep current model or switch to another model now.",
        "  ↳ Recap: Usage limit reached again; try again at 4:00 AM.",
    ],
    ids=["purchase", "downgrade", "limit-words"],
)
def test_recap_with_recognised_prompt_words_fails_closed(recap: str) -> None:
    screen = [*SCREEN[:RECAP_START], recap, *SCREEN[RECAP_START + 4 :]]
    result = providers.CODEX.recognise(screen, now=SEEN)

    assert not result.retry_prompt


@pytest.mark.parametrize(
    "intruder",
    [
        "  1. Yes, proceed",
        "Do you want to continue?",
        GLYPH + " draft text",
        "         nine-space continuation",
    ],
    ids=["menu", "question", "draft", "misindented"],
)
def test_unrecognised_row_in_or_after_recap_fails_closed(intruder: str) -> None:
    for position in (RECAP_START + 2, RECAP_START + 4):
        screen = [*SCREEN[:position], intruder, *SCREEN[position:]]
        result = providers.CODEX.recognise(screen, now=SEEN)

        assert not result.retry_prompt, (intruder, position)


@pytest.mark.parametrize(
    "status",
    [
        "  GPT-6.1-Sol medium · ~/repos/project · Finish work · Main [other]",
        "  GPT-6.1-Sol medium · ~/repos/project · a · b · Main [default]",
        "  GPT-6.1-Sol medium · ~/repos/project · Finish work · Main [default] extra",
    ],
    ids=["other-agent", "extra-segment", "trailing-text"],
)
def test_unobserved_status_row_is_not_an_empty_composer(status: str) -> None:
    screen = [status if "Main [default]" in line else line for line in SCREEN]
    result = providers.CODEX.recognise(screen, now=SEEN)

    assert not result.composer_empty
    assert not result.retry_prompt


def test_draft_in_composer_never_gets_continue() -> None:
    screen = [
        GLYPH + " half-typed instruction" if line.startswith(GLYPH) else line for line in SCREEN
    ]
    result = providers.CODEX.recognise(screen, now=SEEN)

    assert not result.retry_prompt
    assert not result.input_ready


def _setup(tmp_path):
    kit = build(
        tmp_path,
        now=SEEN,
        config=Config(mode=Mode.AUTO, policy=Policy(allow_codex_auto_resume=True)),
    )
    info = kit.inspector.add_codex(3421320)
    ref = kit.terminal.add("/Sessions/1", shell_pid=100, foreground_pid=info.pid, screen=SCREEN)
    kit.supervisor.select(ref, info.identity, "codex", "synthetic")
    kit.quota["codex"].availability = Availability.UNKNOWN
    return kit, kit.supervisor.sessions[ref.key()]


def test_overnight_limit_continues_once_after_its_dated_reset(tmp_path):
    kit, session = _setup(tmp_path)

    result = kit.supervisor.tick()[0]
    assert not result.allowed
    assert session.reset_at == RESET
    assert kit.sent == []

    first = kit.supervisor.config.retry_schedule[0]
    kit.clock.advance((RESET - SEEN).total_seconds() + first - 1)
    kit.supervisor.tick()
    assert kit.sent == []

    kit.clock.advance(1)
    kit.supervisor.tick()
    assert len(kit.sent) == 1
    assert "continue" in kit.sent[0][1]


def test_observe_mode_never_types_into_the_0_167_limit(tmp_path):
    kit = build(
        tmp_path,
        now=SEEN,
        config=Config(mode=Mode.OBSERVE, policy=Policy(allow_codex_auto_resume=True)),
    )
    info = kit.inspector.add_codex(3421320)
    ref = kit.terminal.add("/Sessions/1", shell_pid=100, foreground_pid=info.pid, screen=SCREEN)
    kit.supervisor.select(ref, info.identity, "codex", "synthetic")
    kit.clock.advance((RESET - SEEN).total_seconds() + 3600)
    kit.supervisor.tick()

    assert kit.sent == []
