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

from __future__ import annotations

import contextlib
import fcntl
import os
import pty
import select
import struct
import sys
import termios
import time
from collections.abc import Callable
from pathlib import Path

import pytest

from agent_while_true import whip
from agent_while_true.ui import _PALETTES, whip_role

ROOT = Path(__file__).resolve().parents[1]
COLUMNS, ROWS = 120, 32

pytestmark = pytest.mark.e2e


class Dashboard:
    """One real dashboard process on a pseudo-terminal."""

    def __init__(self, home: Path, *arguments: str, env: dict[str, str] | None = None) -> None:
        runtime = home / "run"
        runtime.mkdir(mode=0o700, parents=True, exist_ok=True)
        environment = {
            "PATH": str(Path(sys.executable).parent),
            "PYTHONPATH": str(ROOT / "src"),
            "HOME": str(home),
            "XDG_STATE_HOME": str(home / "state"),
            "XDG_CONFIG_HOME": str(home / "config"),
            "XDG_RUNTIME_DIR": str(runtime),
            "TERM": "xterm-256color",
            # The provider status poll must not reach the network from a test:
            # a proxy on a closed local port fails it at once, as UNKNOWN.
            "http_proxy": "http://127.0.0.1:9",
            "https_proxy": "http://127.0.0.1:9",
            **(env or {}),
        }
        command = [sys.executable, "-m", "agent_while_true.cli", "run", "--observe", "--all"]
        self.pid, self.fd = pty.fork()
        if self.pid == 0:  # pragma: no cover - the child process
            os.execve(sys.executable, [*command, *arguments], environment)
        fcntl.ioctl(self.fd, termios.TIOCSWINSZ, struct.pack("HHHH", ROWS, COLUMNS, 0, 0))
        self.output = b""

    @property
    def text(self) -> str:
        return self.output.decode(errors="replace")

    def read_until(self, done: Callable[[str], bool], timeout: float = 10.0) -> str:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if done(self.text):
                return self.text
            ready, _, _ = select.select([self.fd], [], [], 0.05)
            if ready:
                try:
                    self.output += os.read(self.fd, 65536)
                except OSError:
                    break
        raise AssertionError(f"dashboard never reached the expected state:\n{self.text[-2000:]}")

    def press(self, key: str) -> None:
        os.write(self.fd, key.encode())

    def switch_theme(self, theme: str) -> None:
        """Press t once and wait for the dashboard to redraw in ``theme``."""
        start = len(self.text)
        self.press("t")
        self.read_until(lambda text: f"theme={theme}" in text[start:])

    def quit(self) -> int:
        self.press("q")
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            finished, status = os.waitpid(self.pid, os.WNOHANG)
            if finished:
                return os.waitstatus_to_exitcode(status)
            ready, _, _ = select.select([self.fd], [], [], 0.05)
            if ready:
                with contextlib.suppress(OSError):
                    self.output += os.read(self.fd, 65536)
        os.kill(self.pid, 9)
        raise AssertionError("dashboard did not quit")


def _crack_in(dashboard: Dashboard, number: int) -> str:
    """Press w and return the output of exactly that crack, up to its redraw."""
    start = len(dashboard.text)
    dashboard.press("w")
    dashboard.read_until(lambda text: f"whip={number} sent=0" in text[start:])
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
