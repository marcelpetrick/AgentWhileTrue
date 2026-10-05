# SPDX-FileCopyrightText: 2026 Marcel Petrick
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The version string, the changelog and the packaging metadata must agree.

Every commit in this project bumps the version, so the cheapest way to keep that
promise honest is to fail the build when the changelog forgets.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import agent_while_true

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SEMVER = re.compile(r"^\d+\.\d+\.\d+$")


def _newest_changelog_version() -> str:
    changelog = (PROJECT_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    match = re.search(r"^## \[(?P<version>[^\]]+)\]", changelog, flags=re.MULTILINE)
    assert match is not None, "CHANGELOG.md has no versioned section"
    return match.group("version")


def test_version_is_semver() -> None:
    assert SEMVER.match(agent_while_true.__version__), agent_while_true.__version__


def test_changelog_documents_current_version() -> None:
    assert _newest_changelog_version() == agent_while_true.__version__


def test_pyproject_takes_version_from_the_package() -> None:
    pyproject = (PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert 'version = { attr = "agent_while_true.version.__version__" }' in pyproject


def test_distribution_supports_exactly_python_3_14() -> None:
    project = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    assert project["project"]["requires-python"] == ">=3.14,<3.15"
    assert "Programming Language :: Python :: 3.14" in project["project"]["classifiers"]
    assert project["tool"]["ruff"]["target-version"] == "py314"
    assert project["tool"]["mypy"]["python_version"] == "3.14"


def test_distribution_declares_and_ships_gplv3_or_later() -> None:
    pyproject = (PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    license_text = (PROJECT_ROOT / "LICENSE").read_text(encoding="utf-8")
    assert 'license = "GPL-3.0-or-later"' in pyproject
    assert 'license-files = ["LICENSE"]' in pyproject
    assert "GNU GENERAL PUBLIC LICENSE" in license_text
    assert "Version 3, 29 June 2007" in license_text
