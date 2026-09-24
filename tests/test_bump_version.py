# SPDX-FileCopyrightText: 2026 Marcel Petrick
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The version bump helper edits the version and changelog together or not at all."""

from __future__ import annotations

import importlib.util
import io
import sys
from datetime import date
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parents[1] / "scripts" / "bump_version.py"
_spec = importlib.util.spec_from_file_location("bump_version", SCRIPT)
assert _spec is not None
assert _spec.loader is not None
bump_version = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bump_version)


def _project(tmp_path: Path, version: str = "0.50.8") -> Path:
    package = tmp_path / "src" / "agent_while_true"
    package.mkdir(parents=True)
    (package / "version.py").write_text(f'"""V."""\n\n__version__ = "{version}"\n')
    (tmp_path / "CHANGELOG.md").write_text("# Changelog\n\nIntro.\n\n## [0.50.8] - 2026-09-22\n")
    return tmp_path


def test_bump_writes_version_and_newest_section(tmp_path: Path) -> None:
    root = _project(tmp_path)
    bump_version.bump(root, "0.51.0", "Added", "- The whip.\n", date(2026, 9, 24))

    assert '__version__ = "0.51.0"' in (root / "src/agent_while_true/version.py").read_text()
    assert (root / "CHANGELOG.md").read_text() == (
        "# Changelog\n\nIntro.\n\n## [0.51.0] - 2026-09-24\n\n### Added\n\n- The whip.\n\n"
        "## [0.50.8] - 2026-09-22\n"
    )


@pytest.mark.parametrize(
    ("version", "category", "body", "message"),
    [
        ("0.50.8", "Added", "- x", "not newer"),
        ("0.49.9", "Added", "- x", "not newer"),
        ("1.0", "Added", "- x", "MAJOR.MINOR.PATCH"),
        ("0.51.0", "Stuff", "- x", "category"),
        ("0.51.0", "Fixed", "  \n", "empty"),
    ],
)
def test_bump_refuses_without_writing(
    tmp_path: Path, version: str, category: str, body: str, message: str
) -> None:
    root = _project(tmp_path)
    before = (root / "CHANGELOG.md").read_text()
    with pytest.raises(ValueError, match=message):
        bump_version.bump(root, version, category, body, date(2026, 9, 24))
    assert (root / "CHANGELOG.md").read_text() == before
    assert '"0.50.8"' in (root / "src/agent_while_true/version.py").read_text()


def test_bump_refuses_malformed_project_files(tmp_path: Path) -> None:
    root = _project(tmp_path)
    (root / "CHANGELOG.md").write_text("# Changelog\n")
    with pytest.raises(ValueError, match="no version section"):
        bump_version.bump(root, "0.51.0", "Added", "- x", date(2026, 9, 24))
    (root / "src/agent_while_true/version.py").write_text("VERSION = 1\n")
    with pytest.raises(ValueError, match="no __version__"):
        bump_version.bump(root, "0.51.0", "Added", "- x", date(2026, 9, 24))


def test_main_reports_success_and_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _project(tmp_path)
    monkeypatch.setattr(sys, "stdin", io.StringIO("- Fixed it.\n"))
    assert bump_version.main(["0.50.9", "Fixed", "--root", str(root)]) == 0
    assert "bumped to 0.50.9" in capsys.readouterr().out

    monkeypatch.setattr(sys, "stdin", io.StringIO("- Again.\n"))
    assert bump_version.main(["0.50.9", "Fixed", "--root", str(root)]) == 1
    assert "not newer" in capsys.readouterr().err
