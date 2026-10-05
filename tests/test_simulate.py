# SPDX-FileCopyrightText: 2026 Marcel Petrick
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The safety scenarios are assertions, not demonstrations.

Section 40 of the vision lists the situations that must be exercised; this test
fails the build if any of them stops holding.
"""

import io
from pathlib import Path

import pytest

from agent_while_true import simulate
from agent_while_true.cli import EXIT_ERROR, EXIT_OK, main


@pytest.mark.parametrize("name", sorted(simulate.SCENARIOS))
def test_every_scenario_holds(name: str, tmp_path: Path) -> None:
    result = simulate.run(name, tmp_path)
    assert result.passed, result.render()


def test_the_happy_path_actually_sends_something(tmp_path: Path) -> None:
    # A suite of scenarios that all pass by never typing would prove nothing.
    result = simulate.run("reset-and-resume", tmp_path)
    assert result.sent == [(simulate.SESSION, "\r")]


#: The only scenarios that are supposed to type, and exactly what they type.
TALKATIVE = {
    "reset-and-resume": [(simulate.SESSION, "\r")],
    "reset-delayed-90s": [(simulate.SESSION, "\r")],
    "continue-still-blocked": [(simulate.SESSION, "\r")],
    "duplicate-prompt": [(simulate.SESSION, "\r")],
    "wait-menu-gauge-says-available": [(simulate.SESSION, "\x1b[B\r")],
    # Auto-yes switched on by the operator answers one exact permission menu.
    "auto-yes-answers-once": [(simulate.SESSION, "\r")],
    # An answered box that stays gets exactly one more Enter, never a third.
    "auto-yes-resends-once": [(simulate.SESSION, "\r"), (simulate.SESSION, "\r")],
}


#: Every case named by vision section 40 stays tied to an executable scenario.
VISION_40_CASES = {
    "limit reached": "reset-and-resume",
    "reset after 30 seconds": "reset-and-resume",
    "reset delayed by 90 seconds": "reset-delayed-90s",
    "weekly limit still active": "weekly-limit-still-blocked",
    "provider API unavailable": "provider-unavailable",
    "prompt changed": "prompt-changed-before-send",
    "terminal closed": "terminal-closed",
    "process restarted": "process-restarted",
    "PID reused": "pid-reused",
    "session replaced": "session-replaced",
    "laptop suspend": "suspend-across-reset",
    "duplicate event": "duplicate-prompt",
    "watcher crash": "crash-recovery",
    "continue fails": "continue-still-blocked",
    "continue succeeds": "reset-and-resume",
    "unknown menu": "unknown-menu",
    "paid credits prompt": "paid-credits-prompt",
    "model downgrade prompt": "model-downgrade-prompt",
}


def test_every_other_scenario_stays_silent(tmp_path: Path) -> None:
    for name in simulate.SCENARIOS:
        expected = TALKATIVE.get(name, [])
        assert simulate.run(name, tmp_path).sent == expected, name


def test_scenarios_are_documented() -> None:
    for name, description in simulate.catalogue():
        assert description, name
        assert name in simulate.SCENARIOS


def test_every_vision_40_case_has_a_registered_scenario() -> None:
    assert len(VISION_40_CASES) == 18
    assert set(VISION_40_CASES.values()) <= set(simulate.SCENARIOS)


def test_cli_lists_scenarios() -> None:
    out = io.StringIO()
    assert main(["simulate"], stream=out) == EXIT_OK
    assert "agent-exited" in out.getvalue()


def test_cli_runs_one_scenario() -> None:
    out = io.StringIO()
    assert main(["simulate", "agent-exited"], stream=out) == EXIT_OK
    assert "result     PASS" in out.getvalue()
    assert "DANGER 2" in out.getvalue()


def test_cli_runs_them_all() -> None:
    out = io.StringIO()
    assert main(["simulate", "--all"], stream=out) == EXIT_OK
    assert out.getvalue().count("PASS") == len(simulate.SCENARIOS)


def test_cli_rejects_an_unknown_scenario() -> None:
    out = io.StringIO()
    assert main(["simulate", "no-such-thing"], stream=out) == EXIT_ERROR
