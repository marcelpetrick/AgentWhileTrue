#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Marcel Petrick
# SPDX-License-Identifier: GPL-3.0-or-later
"""Bump the project version and open the matching newest changelog section.

Every versioned commit edits the same two places: ``__version__`` in
``src/agent_while_true/version.py`` and a new top section in ``CHANGELOG.md``.
This script does both in one step so the pair cannot drift::

    scripts/bump_version.py 0.51.0 Added < notes.md
    printf -- '- Fix the thing.\\n' | scripts/bump_version.py 0.50.9 Fixed

The changelog body is read from standard input and placed under a
``### <category>`` heading (Keep a Changelog: Added, Changed, Deprecated,
Removed, Fixed, Security). The new version must be strictly greater than the
current one; nothing is written when any check fails.
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CATEGORIES = ("Added", "Changed", "Deprecated", "Removed", "Fixed", "Security")
SEMVER = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")
VERSION_LINE = re.compile(r'^__version__ = "(?P<version>[^"]+)"$', re.MULTILINE)
FIRST_SECTION = re.compile(r"^## \[", re.MULTILINE)


def _parse(version: str) -> tuple[int, int, int]:
    match = SEMVER.match(version)
    if match is None:
        raise ValueError(f"not a MAJOR.MINOR.PATCH version: {version!r}")
    major, minor, patch = (int(part) for part in match.groups())
    return major, minor, patch


def bump(root: Path, version: str, category: str, body: str, today: date) -> None:
    """Rewrite the version module and prepend the changelog section."""
    if category not in CATEGORIES:
        raise ValueError(f"category must be one of {', '.join(CATEGORIES)}")
    if not body.strip():
        raise ValueError("the changelog body on standard input is empty")
    version_file = root / "src" / "agent_while_true" / "version.py"
    changelog = root / "CHANGELOG.md"
    source = version_file.read_text(encoding="utf-8")
    current = VERSION_LINE.search(source)
    if current is None:
        raise ValueError(f"no __version__ line in {version_file}")
    if _parse(version) <= _parse(current.group("version")):
        raise ValueError(f"{version} is not newer than {current.group('version')}")
    history = changelog.read_text(encoding="utf-8")
    first = FIRST_SECTION.search(history)
    if first is None:
        raise ValueError(f"no version section in {changelog}")
    section = f"## [{version}] - {today.isoformat()}\n\n### {category}\n\n{body.strip()}\n\n"
    version_file.write_text(
        VERSION_LINE.sub(f'__version__ = "{version}"', source, count=1), encoding="utf-8"
    )
    changelog.write_text(
        history[: first.start()] + section + history[first.start() :], encoding="utf-8"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("version", help="the new MAJOR.MINOR.PATCH version")
    parser.add_argument("category", choices=CATEGORIES, help="changelog subsection heading")
    parser.add_argument("--root", type=Path, default=ROOT, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    try:
        bump(args.root, args.version, args.category, sys.stdin.read(), date.today())
    except (OSError, ValueError) as exc:
        print(f"bump_version: {exc}", file=sys.stderr)
        return 1
    print(f"bumped to {args.version}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
