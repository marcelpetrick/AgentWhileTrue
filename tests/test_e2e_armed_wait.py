# SPDX-FileCopyrightText: 2026 Marcel Petrick
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""A real PTY must show the waiting footer as blocked, never active."""

from pathlib import Path

import pytest

from tests.pty_dashboard import Dashboard

pytestmark = pytest.mark.e2e


def test_agent_panel_does_not_hide_the_wait_in_the_real_dashboard(tmp_path: Path) -> None:
    dashboard = Dashboard(tmp_path, driver=Path(__file__).with_name("pty_armed_wait.py"))
    try:
        dashboard.read_until(lambda text: "LIMIT_BLOCKED" in text)
        assert "[A] auto-resume on limit: OFF" in dashboard.text
        assert "/usage-credits" not in dashboard.text
    finally:
        assert dashboard.quit() == 0
