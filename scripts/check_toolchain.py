#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Marcel Petrick
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Check that the quality toolchain in use is exactly the one pyproject.toml pins.

``localPipeline.sh`` used to accept any ``ruff``, ``pytest`` or ``reuse`` found on
``PATH``. A stray ``~/.local/bin/ruff`` 0.15.20 therefore linted every local run
while the pin said 0.16.9, and nothing reported it. This check compares both
the distributions installed for this interpreter and the version each command
on ``PATH`` prints against the pins, and names every mismatch. Exit status 0
means the toolchain is exactly the pinned one; 1 means the pipeline must
provision its own.
"""

import re
import shutil
import subprocess
import sys
import tomllib
from collections.abc import Callable
from importlib import metadata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
#: Commands the gate runs from PATH, and the distribution that provides each.
COMMANDS = {"ruff": "ruff", "mypy": "mypy", "pytest": "pytest", "reuse": "reuse"}
_PIN = re.compile(r"^\s*(?P<name>[A-Za-z0-9_.-]+)(?:\[[^\]]*\])?\s*==\s*(?P<version>[^\s;]+)")


def pins(pyproject: Path) -> dict[str, str]:
    """The exact ``name==version`` pins of the dev extra, names normalised."""
    project = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    found = {}
    for requirement in project["project"]["optional-dependencies"]["dev"]:
        match = _PIN.match(requirement)
        if match is None:
            raise ValueError(f"not an exact pin: {requirement}")
        found[_normalise(match.group("name"))] = match.group("version")
    return found


def _normalise(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _installed(name: str) -> str | None:
    try:
        return metadata.version(name)
    except metadata.PackageNotFoundError:
        return None


def _command_version(command: str) -> str | None:
    """The output of ``command --version``, or None when it is not on PATH."""
    path = shutil.which(command)
    if path is None:
        return None
    try:
        result = subprocess.run(
            [path, "--version"], capture_output=True, text=True, timeout=30, check=False
        )
    except OSError, subprocess.SubprocessError:
        return ""
    return f"{result.stdout}\n{result.stderr}"


def mismatches(
    wanted: dict[str, str],
    *,
    installed: Callable[[str], str | None] = _installed,
    command_version: Callable[[str], str | None] = _command_version,
) -> list[str]:
    """Every way the toolchain in use differs from ``wanted``; empty when exact."""
    problems = []
    for name, version in sorted(wanted.items()):
        actual = installed(name)
        if actual is None:
            problems.append(f"{name} {version} is not installed")
        elif actual != version:
            problems.append(f"{name} {actual} is installed, pinned {version}")
    for command, distribution in COMMANDS.items():
        version = wanted.get(distribution)
        if version is None:
            continue
        output = command_version(command)
        if output is None:
            # quality.sh falls back to `python -m`, which the check above covers.
            continue
        if not re.search(rf"(?<![\w.]){re.escape(version)}(?![\w.])", output):
            shown = " ".join(output.split())[:60] or "no version"
            problems.append(f"{command} on PATH reports {shown!r}, pinned {version}")
    return problems


def main(argv: list[str] | None = None) -> int:
    arguments = sys.argv[1:] if argv is None else argv
    pyproject = Path(arguments[0]) if arguments else ROOT / "pyproject.toml"
    problems = mismatches(pins(pyproject))
    for problem in problems:
        print(f"[INFO] toolchain: {problem}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
