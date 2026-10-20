# SPDX-FileCopyrightText: 2026 Marcel Petrick
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Offline PTY driver for permission diagnostics.

Invoked by Dashboard(driver=...) with its temporary-home argument and optional
``conflict`` case argument. Fake terminal,
process and quota inputs exercise the real observe dashboard; output is its UI.
No host terminal, credentials or provider settings are read, and no input is sent.
"""

import sys
from pathlib import Path

from agent_while_true import cli
from agent_while_true.config import Mode
from agent_while_true.lock import SingleInstanceLock
from tests import harness, screens


def main() -> int:
    home = Path(sys.argv[1])
    kit = harness.build(home, mode=Mode.OBSERVE)
    screen = list(screens.CLAUDE_APPROVAL_CURSOR_ON_TWO)
    if len(sys.argv) > 2 and sys.argv[2] == "conflict":
        screen = list(screens.CLAUDE_APPROVAL_YES_NO)
        screen.insert(2, "Switch to another model")
    info = kit.inspector.add_claude(4101)
    ref = kit.terminal.add(
        "/Sessions/1",
        shell_pid=100,
        foreground_pid=info.pid,
        screen=screen,
    )
    kit.supervisor.select(ref, info.identity, "claude", "synthetic permission")
    args = cli.build_parser().parse_args(["run", "--observe"])
    lock = SingleInstanceLock.in_directory(home / "runtime")
    result = cli._loop(kit.supervisor, kit.supervisor.config, args, sys.stdout, lock)
    assert kit.sent == []
    return result


if __name__ == "__main__":
    raise SystemExit(main())
