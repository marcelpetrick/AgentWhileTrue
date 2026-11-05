# SPDX-FileCopyrightText: 2026 Marcel Petrick
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Regression for a privacy-redacted live Claude permission warning."""

from datetime import datetime
from zoneinfo import ZoneInfo

from agent_while_true.providers import CLAUDE
from agent_while_true.states import SessionState


def test_clipped_security_warning_is_not_an_automatic_approval() -> None:
    # Observed on Claude 2.1.318 in an 80-row Konsole read on 2026-11-05.
    # Preview, account details and task-specific text are replaced; the
    # provider's warning and the relative menu/frame positions are retained.
    screen = ["[redacted preview]"] * 69 + [
        "┄" * 80,
        " │ [redacted] requires confirmation for this [redacted]",
        " │ This call's input holds your account email address, which may leave this machine. "
        "If nobody asked to send it, go on without it.",
        " │ [redacted]",
        " [redacted]",
        "",
        "Do you want to proceed?",
        "\u276f 1. Yes",
        "  2. No",
        "",
        "Esc to cancel",
    ]
    result = CLAUDE.recognise(screen, now=datetime(2026, 11, 5, tzinfo=ZoneInfo("Europe/Berlin")))

    assert len(screen) == 80
    assert result.state is SessionState.APPROVAL_PENDING
    assert not result.approval_prompt
    assert result.action is None
