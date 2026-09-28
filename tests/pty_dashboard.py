# SPDX-FileCopyrightText: 2026 Marcel Petrick
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The real CLI on a pseudo-terminal, shared by the end-to-end tests.

``Dashboard`` starts ``agent-while-true run --observe --all`` as a separate
process on a pseudo-terminal, exactly as a person would in Konsole, and drives
it with key presses. ``PATH`` holds only the Python interpreter, so there is no
``qdbus`` and therefore no Konsole: the dashboard runs with no sessions and
observe mode, so nothing can ever be typed anywhere. State, configuration and
runtime directories live under the caller's temporary directory, and the
provider status poll is pointed at a closed local proxy, so no test reaches
the network.
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

ROOT = Path(__file__).resolve().parents[1]
COLUMNS, ROWS = 120, 32


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
