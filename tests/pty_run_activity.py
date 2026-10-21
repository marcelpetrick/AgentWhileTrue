# SPDX-FileCopyrightText: 2026 Marcel Petrick
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Offline PTY fixture: real own-action counts and human history, no host access.

Dashboard(driver=...) supplies an isolated temporary-home argument. Seed one
real fake-terminal approval, then run the unchanged interactive loop in observe
mode. Output is synthetic; no host terminal or credential is read or modified.
"""

import sys
from dataclasses import replace
from pathlib import Path

from agent_while_true import cli
from agent_while_true.config import Mode
from agent_while_true.lock import SingleInstanceLock
from tests import harness, screens


def main() -> int:
    home = Path(sys.argv[1])
    kit = harness.build(home)
    info = kit.inspector.add_claude(15102)
    ref = kit.terminal.add(
        "/Sessions/1",
        shell_pid=100,
        foreground_pid=15102,
        screen=list(screens.CLAUDE_APPROVAL_YES_NO),
    )
    kit.supervisor.select(ref, info.identity, "claude", "invented project")
    kit.supervisor.tick()
    assert kit.supervisor.approve_pending()[ref.key()] == "approved"
    kit.terminal.set_screen("/Sessions/1", list(screens.CLAUDE_ACTIVE))
    codex = kit.inspector.add_codex(15202)
    capacity_ref = kit.terminal.add(
        "/Sessions/2",
        shell_pid=101,
        foreground_pid=15202,
        screen=list(screens.CODEX_MODEL_CAPACITY),
    )
    kit.supervisor.select(capacity_ref, codex.identity, "codex", "invented capacity project")
    kit.supervisor.tick()
    kit.clock.advance(5)
    harness.refresh_quota(kit)
    kit.supervisor.tick()
    assert kit.supervisor.activity.capacity_recoveries == 0
    kit.terminal.set_screen("/Sessions/2", list(screens.CODEX_ACTIVE))
    kit.clock.advance(1)
    harness.refresh_quota(kit)
    kit.supervisor.tick()
    assert kit.supervisor.activity.capacity_recoveries == 0
    kit.clock.advance(3)
    harness.refresh_quota(kit)
    kit.supervisor.tick()
    assert kit.supervisor.activity.capacity_recoveries == 1
    assert kit.supervisor.activity.budget_restarts == 0
    assert kit.supervisor.activity.unblock_actions == 2
    kit.supervisor.config = replace(kit.supervisor.config, mode=Mode.OBSERVE)
    args = cli.build_parser().parse_args(["run", "--observe", "--all"])
    lock = SingleInstanceLock.in_directory(home / "runtime")
    result = cli._loop(kit.supervisor, kit.supervisor.config, args, sys.stdout, lock)
    assert kit.sent == [
        ("/Sessions/1", "\r"),
        ("/Sessions/2", "\x1b[200~continue\x1b[201~\r"),
    ]
    return result


if __name__ == "__main__":
    raise SystemExit(main())
