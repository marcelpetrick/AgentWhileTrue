# SPDX-FileCopyrightText: 2026 Marcel Petrick
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Documentation links must stay valid in the standalone repository layout."""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import unquote, urlsplit

PROJECT_ROOT = Path(__file__).resolve().parent.parent
LINK = re.compile(r"\]\((?P<target>[^)]+)\)")


def _markdown_files() -> list[Path]:
    return sorted([*PROJECT_ROOT.glob("*.md"), *(PROJECT_ROOT / "docs").rglob("*.md")])


def test_relative_documentation_links_exist() -> None:
    missing: list[str] = []
    for document in _markdown_files():
        for match in LINK.finditer(document.read_text(encoding="utf-8")):
            target = match.group("target").split(maxsplit=1)[0].strip("<>")
            parsed = urlsplit(target)
            if parsed.scheme or parsed.netloc or not parsed.path:
                continue
            linked_path = document.parent / unquote(parsed.path)
            if not linked_path.exists():
                missing.append(f"{document.relative_to(PROJECT_ROOT)}: {target}")

    assert not missing, "broken relative documentation links:\n" + "\n".join(missing)


def test_documentation_has_no_old_monorepo_links() -> None:
    old_location = "github.com/marcelpetrick/codingWithGPT/tree/master/AgentWhileTrue"
    offenders = [
        document.name
        for document in _markdown_files()
        if old_location in document.read_text(encoding="utf-8")
    ]
    assert not offenders, f"old monorepo links remain in: {', '.join(offenders)}"


def test_superseded_project_names_are_absent_from_the_shipped_tree() -> None:
    forbidden = ("agent" + "-watch", "agent" + "_watch", "agent" + " watch")
    roots = [
        PROJECT_ROOT / ".github",
        PROJECT_ROOT / "docs",
        PROJECT_ROOT / "scripts",
        PROJECT_ROOT / "src",
        PROJECT_ROOT / "systemd",
        PROJECT_ROOT / "tests",
    ]
    files = [
        PROJECT_ROOT / "AGENTS.md",
        PROJECT_ROOT / "CHANGELOG.md",
        PROJECT_ROOT / "README.md",
        PROJECT_ROOT / "fullAutoMode.sh",
        PROJECT_ROOT / "localPipeline.sh",
        PROJECT_ROOT / "pyproject.toml",
    ]
    files.extend(path for root in roots for path in root.rglob("*") if path.is_file())

    offenders: list[str] = []
    for path in files:
        try:
            contents = path.read_text(encoding="utf-8").lower()
        except UnicodeDecodeError:
            continue
        if any(name in contents for name in forbidden):
            offenders.append(str(path.relative_to(PROJECT_ROOT)))

    assert not offenders, "superseded project names remain in: " + ", ".join(offenders)
    assert not (PROJECT_ROOT / "src" / ("agent" + "_watch")).exists()
    assert not (PROJECT_ROOT / "systemd" / ("agent" + "-watch.service")).exists()
