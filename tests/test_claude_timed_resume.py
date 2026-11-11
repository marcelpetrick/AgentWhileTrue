# SPDX-FileCopyrightText: 2026 Marcel Petrick
# SPDX-License-Identifier: GPL-3.0-or-later
"""Bounded timed continuation of Claude's exact window-limit composer.

The maintainer asked on 2026-11-11 that a limit is always continued once its
printed reset has passed, for Claude as for Codex, while nothing paid is ever
chosen. Only the exact banner-above-empty-composer shape qualifies.
"""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from agent_while_true import providers
from agent_while_true.config import Config, Mode, Policy
from agent_while_true.providers.base import ActionKind
from agent_while_true.quota import Availability, QuotaWindow
from agent_while_true.states import SessionState
from tests import screens
from tests.harness import build

BERLIN = ZoneInfo("Europe/Berlin")
SEEN = datetime(2026, 11, 10, 19, 32, tzinfo=BERLIN)
RESET = datetime(2026, 11, 10, 20, 10, tzinfo=BERLIN)
SCREEN = screens.CLAUDE_LIMIT_COMPOSER
GLYPH = "\N{HEAVY RIGHT-POINTING ANGLE QUOTATION MARK ORNAMENT}"
WORKING = [
    f"{GLYPH} continue",
    "● Picking up the quality gate again.",
    "✻ Cooking… (4s · esc to interrupt)",
    *SCREEN[-5:],
]


def test_exact_limit_composer_proposes_continue() -> None:
    result = providers.CLAUDE.recognise(SCREEN, now=SEEN)

    assert result.state is SessionState.LIMIT_BLOCKED
    assert result.retry_prompt
    assert result.composer_empty
    assert result.reset_at == RESET
    assert result.action is not None
    assert result.action.kind is ActionKind.TEXT_THEN_ENTER
    assert result.action.text == "continue"
    assert result.action.requires_policy == "allow_claude_timed_resume"


def _with(rows: list[str]) -> list[str]:
    """Insert rows between the turn summary and the composer's top rule."""
    return [*SCREEN[:5], *rows, *SCREEN[5:]]


@pytest.mark.parametrize(
    "screen",
    [
        pytest.param(screens.CLAUDE_LIMIT_MENU, id="wait-menu"),
        pytest.param(screens.CLAUDE_LIMIT_MENU_WITH_CREDIT_LINKS, id="wait-menu-links"),
        pytest.param(screens.CLAUDE_CONTINUING_SHORTLY, id="armed-wait"),
        pytest.param(_with(["   What do you want to do?"]), id="question"),
        pytest.param(_with(["     3. Upgrade your plan"]), id="upgrade-item"),
        pytest.param(_with(["  Reset your session limit now"]), id="reset-credit"),
        pytest.param(_with(["  You're out of usage credits"]), id="credits"),
        pytest.param(_with(["  Switch to another model"]), id="model-change"),
        pytest.param(_with(["  some unrecognised row"]), id="unknown-row"),
        pytest.param(
            [line.replace(f"{GLYPH} ", f"{GLYPH} half a draft") for line in SCREEN], id="draft"
        ),
        pytest.param(
            [line.replace(" · resets 8:10pm (Europe/Berlin)", "") for line in SCREEN],
            id="no-reset",
        ),
        pytest.param(
            [
                line.replace("session limit", "monthly spend limit").replace(
                    " · resets 8:10pm (Europe/Berlin)", ""
                )
                for line in SCREEN
            ],
            id="spend-cap",
        ),
    ],
)
def test_every_other_shape_stays_manual(screen: list[str]) -> None:
    result = providers.CLAUDE.recognise(screen, now=SEEN)

    assert not result.retry_prompt
    assert "claude/limit-composer" not in result.matched_ids


def _setup(tmp_path, *, mode=Mode.AUTO, policy=None):
    kit = build(tmp_path, now=SEEN, config=Config(mode=mode, policy=policy or Policy()))
    info = kit.inspector.add_claude(4242)
    ref = kit.terminal.add("/Sessions/1", shell_pid=100, foreground_pid=info.pid, screen=SCREEN)
    kit.supervisor.select(ref, info.identity, "claude", "synthetic")
    kit.quota["claude"].availability = Availability.UNKNOWN
    return kit, kit.supervisor.sessions[ref.key()]


def _until(kit, moment: datetime) -> None:
    kit.clock.advance((moment - kit.clock.wall).total_seconds())
    kit.supervisor.tick()


def test_full_auto_types_continue_only_after_reset_and_backoff(tmp_path):
    kit, session = _setup(tmp_path)
    kit.supervisor.tick()
    assert session.reset_at == RESET
    first = kit.supervisor.config.retry_schedule[0]

    _until(kit, RESET + timedelta(seconds=first - 1))
    assert kit.sent == []
    _until(kit, RESET + timedelta(seconds=first))
    assert len(kit.sent) == 1
    assert "continue" in kit.sent[0][1]


def test_returning_limit_waits_for_the_next_backoff_delay(tmp_path):
    kit, session = _setup(tmp_path)
    kit.supervisor.tick()
    schedule = kit.supervisor.config.retry_schedule
    _until(kit, RESET + timedelta(seconds=schedule[0]))
    assert len(kit.sent) == 1
    kit.clock.advance(1)
    kit.supervisor.tick()  # still the same limit: the trial did not land

    kit.clock.advance(schedule[1] - 2)
    kit.supervisor.tick()
    assert len(kit.sent) == 1
    kit.clock.advance(3)
    kit.supervisor.tick()
    assert len(kit.sent) == 2
    assert session.reset_at == RESET


def test_working_twice_three_seconds_apart_completes_the_episode(tmp_path):
    kit, session = _setup(tmp_path)
    kit.supervisor.tick()
    _until(kit, RESET + timedelta(seconds=kit.supervisor.config.retry_schedule[0]))
    episode = session.retry_episode_key
    assert len(kit.sent) == 1

    kit.terminal.set_screen("/Sessions/1", WORKING)
    for delay in (1, 3, 1):
        kit.clock.advance(delay)
        kit.supervisor.tick()
    assert kit.supervisor.store.get_episode(episode).completed
    assert kit.supervisor.activity.budget_restarts == 1


@pytest.mark.parametrize(
    ("mode", "policy"),
    [
        (Mode.ASK, Policy()),
        (Mode.OBSERVE, Policy()),
        (Mode.AUTO, Policy(allow_claude_timed_resume=False)),
    ],
    ids=["ask", "observe", "switched-off"],
)
def test_no_timed_trial_without_full_auto_and_switch(tmp_path, mode, policy):
    kit, _ = _setup(tmp_path, mode=mode, policy=policy)
    kit.supervisor.tick()
    _until(kit, RESET + timedelta(hours=7))

    assert kit.sent == []


def test_fresh_later_exhaustion_vetoes_the_trial(tmp_path):
    kit, _ = _setup(tmp_path)
    kit.supervisor.tick()
    moment = RESET + timedelta(seconds=kit.supervisor.config.retry_schedule[0])
    kit.clock.advance((moment - kit.clock.wall).total_seconds())
    quota = kit.quota["claude"]
    quota.availability = Availability.EXHAUSTED
    quota.observed_at = kit.clock.wall
    quota.windows = (QuotaWindow("weekly", 100, RESET + timedelta(days=3)),)
    kit.supervisor.tick()

    assert kit.sent == []


def test_a_menu_replacing_the_composer_never_gets_continue(tmp_path):
    kit, _ = _setup(tmp_path)
    kit.supervisor.tick()
    kit.terminal.set_screen("/Sessions/1", screens.CLAUDE_LIMIT_MENU_WITHOUT_BANNER)
    _until(kit, RESET + timedelta(hours=7))

    assert not any("continue" in text for _, text in kit.sent)


def test_ask_mode_never_offers_continue_before_the_printed_reset(tmp_path):
    """A fresh gauge saying "available" cannot override the printed reset."""
    kit, _ = _setup(tmp_path, mode=Mode.ASK)
    asked = []
    kit.supervisor.confirm = lambda observation, decision: asked.append(decision) or False
    quota = kit.quota["claude"]
    quota.availability = Availability.AVAILABLE
    quota.observed_at = kit.clock.wall

    decision = kit.supervisor.tick()[0]
    assert asked == []
    assert decision.reason == "usage-not-confirmed-available"
    assert decision.retry_at is not None
    assert decision.retry_at >= RESET
