# SPDX-FileCopyrightText: 2026 Marcel Petrick
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Exact capacity-error recognition, not automatic model selection."""

from datetime import UTC, datetime

import pytest

from agent_while_true import providers
from agent_while_true.providers import ActionKind
from tests import screens

NOW = datetime(2026, 10, 21, tzinfo=UTC)


def test_observed_capacity_has_distinct_same_model_action():
    result = providers.CODEX.recognise(screens.CODEX_MODEL_CAPACITY, now=NOW)
    assert result.state.value == "CAPACITY_BLOCKED"
    assert result.capacity_prompt
    assert result.composer_empty
    assert result.reset_at is None
    assert result.matched_ids == ("codex/model-capacity",)
    assert result.vetoes == ()
    assert not result.retry_prompt
    assert result.action is not None
    assert result.action.kind is ActionKind.TEXT_THEN_ENTER
    assert result.action.text == "continue"
    assert result.action.requires_policy == "allow_codex_capacity_retry"


@pytest.mark.parametrize(
    "replacement",
    [
        "• Searched the web for Selected model is at capacity. Please try a different model.",
        "Selected model is at capacity. Please try a different model.",
        "■ Selected model is busy. Please try a different model.",
        "■ Selected model is at capacity. Please try a different model. Extra warning",
    ],
)
def test_quoted_or_reworded_capacity_has_no_action(replacement):
    result = providers.CODEX.recognise([replacement, *screens.CODEX_MODEL_CAPACITY[1:]], now=NOW)
    assert not result.capacity_prompt
    assert result.action is None


@pytest.mark.parametrize(
    "tail",
    [
        ["\u203a user's existing draft"],
        ["\u203a ", "a multiline draft with 50% left"],
        ["\u203a Ask Codex to do anything", "unknown footer"],
        ["\u203a Ask Codex to do anything", "draft mentioning 50% left"],
        ["\u203a Ask Codex to do anything", "? for shortcuts", "unexpected question?"],
        ["\u203a Ask Codex to do anything"],
        ["\u203a Ask Codex to do anything", "• Working (1s · esc to interrupt)"],
    ],
)
def test_unknown_or_nonempty_composer_cannot_retry(tail):
    result = providers.CODEX.recognise([screens.CODEX_MODEL_CAPACITY[0], "", *tail], now=NOW)
    assert not result.capacity_prompt
    assert result.action is None


@pytest.mark.parametrize(
    "warning",
    [
        "Upgrade to Pro",
        "Switch to another model now",
        "Keep current model",
        "You're out of credits",
        "Would you like to run the following command?",
        "■ You've hit your usage limit. Try again at 8:10 PM.",
    ],
)
def test_conflicting_prompts_never_propose_capacity_retry(warning):
    result = providers.CODEX.recognise(
        [warning, *screens.CODEX_MODEL_CAPACITY],
        now=NOW,
    )
    assert not result.capacity_prompt
    assert result.action is None


def test_new_assistant_output_scopes_out_historical_capacity():
    result = providers.CODEX.recognise(
        [
            screens.CODEX_MODEL_CAPACITY[0],
            "• Working (1s · esc to interrupt)",
            *screens.CODEX_MODEL_CAPACITY[1:],
        ],
        now=NOW,
    )
    assert not result.capacity_prompt
    assert result.action is None


@pytest.mark.parametrize("footer", ["? for shortcuts", "  GPT-6.1-Sol medium · ~/repos/example"])
def test_known_anchored_footer_is_accepted(footer):
    result = providers.CODEX.recognise([*screens.CODEX_MODEL_CAPACITY[:-1], footer], now=NOW)
    assert result.capacity_prompt
    assert result.action is not None


def test_completed_previous_assistant_output_does_not_hide_current_capacity():
    result = providers.CODEX.recognise(
        ["• Finished previous work", "", *screens.CODEX_MODEL_CAPACITY],
        now=NOW,
    )
    assert result.capacity_prompt
    assert not result.active_evidence


def test_generic_question_above_capacity_cannot_be_answered():
    result = providers.CODEX.recognise(
        ["Which model would you like?", *screens.CODEX_MODEL_CAPACITY],
        now=NOW,
    )
    assert not result.capacity_prompt
    assert result.action is None
