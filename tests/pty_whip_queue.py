# SPDX-FileCopyrightText: 2026 Marcel Petrick
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Offline PTY fixture: a whip crack waits for a draft, then lands once.

Dashboard(driver=...) supplies an isolated temporary-home argument. The real
interactive loop runs in full-auto against fake Konsole tabs: one selected
Claude tab with an operator draft, one unwatched Codex tab with an empty
composer. A helper thread clears the draft once the reminder is queued. Output
is synthetic; no host terminal, process or credential is read or modified.
"""

import sys
import threading
import time
from pathlib import Path

from agent_while_true import cli
from agent_while_true.config import Mode
from agent_while_true.lock import SingleInstanceLock
from tests import harness, screens


def main() -> int:
    home = Path(sys.argv[1])
    kit = harness.build(home, mode=Mode.AUTO)
    claude = kit.inspector.add_claude(16101)
    ref = kit.terminal.add(
        "/Sessions/1", shell_pid=100, foreground_pid=16101, screen=list(screens.CLAUDE_DRAFT)
    )
    kit.supervisor.select(ref, claude.identity, "claude", "invented project")
    kit.inspector.add_codex(16202, tty="pts/8")
    kit.terminal.add(
        "/Sessions/2", shell_pid=101, foreground_pid=16202, screen=list(screens.CODEX_ACTIVE)
    )

    def finish_draft() -> None:
        deadline = time.monotonic() + 20
        while not kit.supervisor.whip_queue and time.monotonic() < deadline:
            time.sleep(0.05)
        time.sleep(4.0)  # long enough for a loaded machine to draw the waiting frame
        kit.terminal.set_screen("/Sessions/1", list(screens.CLAUDE_IDLE_COMPOSER))

    threading.Thread(target=finish_draft, daemon=True).start()
    args = cli.build_parser().parse_args(["run"])
    lock = SingleInstanceLock.in_directory(home / "runtime")
    lock.acquire()
    try:
        result = cli._loop(kit.supervisor, kit.supervisor.config, args, sys.stdout, lock)
    finally:
        lock.release()
    sessions = sorted(session for session, _ in kit.sent)
    assert sessions == ["/Sessions/1", "/Sessions/2"], sessions
    return result


if __name__ == "__main__":
    raise SystemExit(main())
