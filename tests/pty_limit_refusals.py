# SPDX-FileCopyrightText: 2026 Marcel Petrick
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Run the real dashboard against isolated synthetic Codex limit screens."""

import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from agent_while_true import cli
from agent_while_true.config import Config, Mode, Policy
from agent_while_true.lock import SingleInstanceLock
from agent_while_true.quota import Availability
from tests import harness, screens


def main() -> int:
    home = Path(sys.argv[1])
    case = sys.argv[2]
    config = Config(mode=Mode.ASK, policy=Policy(allow_codex_auto_resume=True))
    kit = harness.build(
        home,
        config=config,
        now=datetime(2026, 9, 5, 19, 0, tzinfo=ZoneInfo("Europe/Berlin")),
    )
    info = kit.inspector.add_codex(15102)
    screen = list(screens.CODEX_USAGE_LIMIT)
    if case == "unsupported":
        screen.insert(1, "Which option do you choose?")
    ref = kit.terminal.add(
        "/Sessions/1", shell_pid=100, foreground_pid=info.pid, screen=screen, title="synthetic"
    )
    kit.quota["codex"].availability = Availability.UNKNOWN
    kit.supervisor.select(ref, info.identity, "codex", "synthetic")
    kit.supervisor.tick()
    if case == "confirmation":
        kit.clock.advance(7200)
        kit.supervisor.tick()
    expected = {
        "confirmation": "provider-confirmation-required",
        "unsupported": "unsupported-codex-limit-prompt",
    }[case]
    assert kit.supervisor.sessions[ref.key()].last_reason == expected
    args = cli.build_parser().parse_args(["run", "--all", "--no-color"])
    lock = SingleInstanceLock.in_directory(home / "runtime")
    result = cli._loop(kit.supervisor, kit.supervisor.config, args, sys.stdout, lock)
    assert kit.sent == []
    return result


if __name__ == "__main__":
    raise SystemExit(main())
