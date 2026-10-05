# SPDX-FileCopyrightText: 2026 Marcel Petrick
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""End to end: the real CLI in a pseudo-terminal, cracking the whip in every theme.

Each test starts ``agent-while-true run --observe --all`` as a separate process
on a pseudo-terminal, exactly as a person would in Konsole, and drives it with
key presses. ``PATH`` holds only the Python interpreter, so there is no
``qdbus`` and therefore no Konsole: the dashboard runs with no sessions and
observe mode, so nothing can ever be typed anywhere. State, configuration and
runtime directories live under pytest's temporary directory, and the provider
status poll is pointed at a closed local proxy, so no test reaches the network.
"""

from pathlib import Path

import pytest

from agent_while_true import whip
from agent_while_true.ui import _PALETTES, whip_role
from tests.pty_dashboard import COLUMNS, ROWS, Dashboard

pytestmark = pytest.mark.e2e


def _crack_in(dashboard: Dashboard, number: int) -> str:
    """Press w and return the output of exactly that crack, up to its redraw."""
    start = len(dashboard.text)
    dashboard.press("w")
    # The badge is on the first row and the last-event row comes later in the
    # same frame; wait for both, as a frame arrives in chunks.
    dashboard.read_until(
        lambda text: (
            f"whip={number} sent=0" in text[start:] and "whip cracked in the air" in text[start:]
        )
    )
    return dashboard.text[start:]


def test_every_theme_colours_the_crack_it_draws(tmp_path: Path) -> None:
    """Crack once per theme, switching with t in between, all in one real run."""
    dashboard = Dashboard(tmp_path)
    dashboard.read_until(lambda text: "whip=0 sent=0" in text)
    cracks: dict[str, str] = {}
    for number, theme in enumerate(("dark", "vivid", "cga", "amber"), start=1):
        if number > 1:
            dashboard.switch_theme(theme)
        cracks[theme] = _crack_in(dashboard, number)
    assert dashboard.quit() == 0
    # The closed proxy kept the status poll offline.
    assert "OpenAI: ONLINE" not in dashboard.text

    for theme, output in cracks.items():
        palette = _PALETTES[theme]
        assert palette[whip_role(theme, "handle")] + whip.HANDLE in output, theme
        assert palette[whip_role(theme, "art")] + "____" in output, theme
        # The screen is filled on the theme's own background, not left black.
        assert palette["surface"] + " " * 20 in output, theme
        assert "whip cracked in the air: observe mode sends nothing" in output, theme
        others = [other for other in cracks if other != theme]
        assert not any(
            _PALETTES[other][whip_role(other, "handle")] + whip.HANDLE in output for other in others
        )


def test_the_plain_theme_cracks_in_bare_ascii(tmp_path: Path) -> None:
    dashboard = Dashboard(tmp_path)
    dashboard.read_until(lambda text: "whip=0 sent=0" in text)
    for theme in ("vivid", "cga", "amber", "plain"):
        dashboard.switch_theme(theme)
    output = _crack_in(dashboard, 1)
    assert dashboard.quit() == 0

    crack = output.split("\x1b[H\x1b[2J")[1:-1]
    assert crack, "no animation frames were drawn"
    assert all("\x1b[" not in frame for frame in crack)
    assert any(f"\n{whip.HANDLE}" in frame for frame in crack)


@pytest.mark.parametrize(
    ("arguments", "env"),
    [(("--no-color",), {}), ((), {"NO_COLOR": "1"})],
    ids=["no-color-flag", "NO_COLOR"],
)
def test_colourless_output_cracks_in_bare_ascii(
    tmp_path: Path, arguments: tuple[str, ...], env: dict[str, str]
) -> None:
    dashboard = Dashboard(tmp_path, *arguments, env=env)
    dashboard.read_until(lambda text: "whip=0 sent=0" in text)
    output = _crack_in(dashboard, 1)
    assert dashboard.quit() == 0

    frames = output.split("\x1b[H\x1b[2J")[1:-1]
    assert len(frames) == len(whip.frames(COLUMNS, ROWS - 1))
    assert all("\x1b[" not in frame for frame in frames)
    assert "CRACK" in "".join(frames) or "____" in "".join(frames)
