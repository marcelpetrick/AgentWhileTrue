# SPDX-FileCopyrightText: 2026 Marcel Petrick
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Offline PTY fixture: full-auto keeps the model on Codex's switch dialog.

Dashboard(driver=...) supplies an isolated temporary-home argument. The real
interactive loop runs in full-auto against one fake Codex tab showing the
0.167.0 rate-limit model-switch dialog. A helper thread closes the dialog once
the keypress landed. Output is synthetic; no host terminal, process or
credential is read or modified.
"""

import sys
import threading
import time
from pathlib import Path

from agent_while_true import cli
from agent_while_true.config import Mode
from agent_while_true.fsm import KEEP_MODEL_KEYSTROKES
from agent_while_true.lock import SingleInstanceLock
from tests import harness, screens


def main() -> int:
    home = Path(sys.argv[1])
    kit = harness.build(home, mode=Mode.AUTO)
    codex = kit.inspector.add_codex(17101)
    ref = kit.terminal.add(
        "/Sessions/1",
        shell_pid=100,
        foreground_pid=17101,
        screen=list(screens.CODEX_0_167_KEEP_MODEL_DIALOG),
    )
    kit.supervisor.select(ref, codex.identity, "codex", "invented project")

    def close_dialog() -> None:
        deadline = time.monotonic() + 20
        while not kit.sent and time.monotonic() < deadline:
            time.sleep(0.05)
        time.sleep(4.0)  # long enough for a loaded machine to draw the frame
        kit.terminal.set_screen("/Sessions/1", list(screens.CODEX_0_167_LIMIT_AFTER_KEEP_MODEL))

    threading.Thread(target=close_dialog, daemon=True).start()
    args = cli.build_parser().parse_args(["run"])
    lock = SingleInstanceLock.in_directory(home / "runtime")
    lock.acquire()
    try:
        result = cli._loop(kit.supervisor, kit.supervisor.config, args, sys.stdout, lock)
    finally:
        lock.release()
    assert kit.sent == [("/Sessions/1", KEEP_MODEL_KEYSTROKES)], kit.sent
    return result


if __name__ == "__main__":
    raise SystemExit(main())
