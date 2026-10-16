# SPDX-FileCopyrightText: 2026 Marcel Petrick
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Offline PTY driver for the armed-wait dashboard regression.

Invoked only by ``Dashboard(..., driver=...)`` with one temporary-home argument.
Runs the real interactive loop in observe mode against fake terminal/process
and quota sources. Outputs dashboard frames; never reads host Konsole or sends
provider input. The parent supplies isolated XDG paths and a closed proxy.
"""

import sys
from pathlib import Path

from agent_while_true import cli
from agent_while_true.config import Mode
from agent_while_true.lock import SingleInstanceLock
from agent_while_true.quota import Availability
from tests import harness, screens


def main() -> int:
    home = Path(sys.argv[1])
    kit = harness.build(home, mode=Mode.OBSERVE)
    info = kit.inspector.add_claude(15102)
    ref = kit.terminal.add(
        "/Sessions/1",
        shell_pid=100,
        foreground_pid=info.pid,
        screen=list(screens.CLAUDE_AUTO_WAIT_AGENT_PANEL_2026_10_17),
        title="synthetic armed wait",
    )
    kit.quota["claude"].availability = Availability.EXHAUSTED
    kit.supervisor.select(ref, info.identity, "claude", "synthetic armed wait")
    args = cli.build_parser().parse_args(["run", "--observe", "--all"])
    lock = SingleInstanceLock.in_directory(home / "runtime")
    result = cli._loop(kit.supervisor, kit.supervisor.config, args, sys.stdout, lock)
    assert kit.sent == []
    return result


if __name__ == "__main__":
    raise SystemExit(main())
