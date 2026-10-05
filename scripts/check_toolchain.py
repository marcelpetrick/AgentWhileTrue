#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Marcel Petrick
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Check that the validated interpreter has exactly the pinned quality tools.

The quality gate invokes every Python tool as a module through that interpreter,
so unrelated commands on ``PATH`` cannot participate. Exit status 0 means its
environment is exactly pinned; 1 means the pipeline must provision its own.
"""

import re
import sys
import tomllib
from collections.abc import Callable
from importlib import metadata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
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


def mismatches(
    wanted: dict[str, str],
    *,
    installed: Callable[[str], str | None] = _installed,
) -> list[str]:
    """Every way the toolchain in use differs from ``wanted``; empty when exact."""
    problems = []
    for name, version in sorted(wanted.items()):
        actual = installed(name)
        if actual is None:
            problems.append(f"{name} {version} is not installed")
        elif actual != version:
            problems.append(f"{name} {actual} is installed, pinned {version}")
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
