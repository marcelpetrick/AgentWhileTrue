# SPDX-FileCopyrightText: 2026 Marcel Petrick
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The real dashboard explains Codex limit refusals without sending input."""

from pathlib import Path

import pytest

from tests.pty_dashboard import Dashboard

pytestmark = pytest.mark.e2e


@pytest.mark.parametrize(
    ("case", "message"),
    [
        ("confirmation", "Waiting for fresh provider confirmation of available usage"),
        ("unsupported", "Unrecognized Codex limit screen; inspect the agent tab"),
    ],
)
def test_limit_refusal_explained_in_real_dashboard(tmp_path: Path, case: str, message: str) -> None:
    dashboard = Dashboard(tmp_path, case, driver=Path(__file__).with_name("pty_limit_refusals.py"))
    try:
        dashboard.read_until(lambda text: "LIMIT_BLOCKED" in text)
        start = len(dashboard.text)
        dashboard.press("d")
        dashboard.read_until(
            lambda text: "Last decision:" in text[start:] and message in text[start:]
        )
    finally:
        assert dashboard.quit() == 0
