# SPDX-FileCopyrightText: 2026 Marcel Petrick
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The pipeline accepts a toolchain only when every tool is exactly the pinned one."""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "scripts" / "check_toolchain.py"
_spec = importlib.util.spec_from_file_location("check_toolchain", SCRIPT)
assert _spec is not None
assert _spec.loader is not None
check_toolchain = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(check_toolchain)

WANTED = {"ruff": "0.16.9", "pytest": "9.1.1", "reuse": "6.2.0", "build": "1.6.1"}
EXACT = {"ruff": "ruff 0.16.9", "pytest": "pytest 9.1.1", "reuse": "reuse, version 6.2.0"}


def _problems(installed: dict[str, str | None], commands: dict[str, str | None]) -> list[str]:
    return check_toolchain.mismatches(WANTED, installed=installed.get, command_version=commands.get)


def test_the_repositorys_own_pins_are_all_exact() -> None:
    pins = check_toolchain.pins(ROOT / "pyproject.toml")

    assert {"ruff", "pytest", "reuse", "cyclonedx-python-lib", "spdx-tools"} <= set(pins)
    assert all(version[0].isdigit() for version in pins.values())


def test_a_loose_pin_is_rejected(tmp_path: Path) -> None:
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text('[project.optional-dependencies]\ndev = ["ruff>=0.16"]\n')

    with pytest.raises(ValueError, match="not an exact pin"):
        check_toolchain.pins(pyproject)


def test_extras_and_markers_do_not_hide_the_version(tmp_path: Path) -> None:
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        "[project.optional-dependencies]\n"
        'dev = ["cyclonedx-python-lib[validation]==11.12.0",\n'
        "       \"Spdx_Tools==0.8.5 ; python_version >= '3.12'\"]\n"
    )

    assert check_toolchain.pins(pyproject) == {
        "cyclonedx-python-lib": "11.12.0",
        "spdx-tools": "0.8.5",
    }


def test_the_exact_toolchain_passes() -> None:
    assert _problems(dict(WANTED), dict(EXACT)) == []


def test_a_stray_command_on_path_is_reported_even_when_the_package_matches() -> None:
    """The 2026-09-29 case: ~/.local/bin/ruff 0.15.20 shadowed the pinned 0.16.9."""
    problems = _problems(dict(WANTED), {**EXACT, "ruff": "ruff 0.15.20"})

    assert problems == ["ruff on PATH reports 'ruff 0.15.20', pinned 0.16.9"]


def test_a_wrong_or_missing_package_is_reported() -> None:
    problems = _problems({**WANTED, "build": "1.5.0", "reuse": None}, dict(EXACT))

    assert problems == [
        "build 1.5.0 is installed, pinned 1.6.1",
        "reuse 6.2.0 is not installed",
    ]


def test_a_longer_version_is_not_mistaken_for_the_pin() -> None:
    problems = _problems(dict(WANTED), {**EXACT, "ruff": "ruff 0.16.90"})

    assert problems == ["ruff on PATH reports 'ruff 0.16.90', pinned 0.16.9"]


def test_a_command_missing_from_path_falls_back_to_the_package_check() -> None:
    assert _problems(dict(WANTED), {**EXACT, "reuse": None}) == []


def test_the_script_names_a_stray_command_and_fails(tmp_path: Path) -> None:
    """Run as the pipeline does, with a fake ruff first on PATH."""
    fake = tmp_path / "bin" / "ruff"
    fake.parent.mkdir()
    fake.write_text("#!/bin/sh\necho 'ruff 0.0.1'\n")
    fake.chmod(0o755)
    environment = {**os.environ, "PATH": f"{fake.parent}{os.pathsep}{os.environ['PATH']}"}

    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(ROOT / "pyproject.toml")],
        capture_output=True,
        text=True,
        env=environment,
        timeout=60,
        check=False,
    )

    assert result.returncode == 1
    assert "ruff on PATH reports 'ruff 0.0.1'" in result.stdout
