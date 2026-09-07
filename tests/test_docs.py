"""Documentation links must stay valid in the standalone repository layout."""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import unquote, urlsplit

PROJECT_ROOT = Path(__file__).resolve().parent.parent
LINK = re.compile(r"\]\((?P<target>[^)]+)\)")


def _markdown_files() -> list[Path]:
    return sorted(PROJECT_ROOT.glob("*.md"))


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
                missing.append(f"{document.name}: {target}")

    assert not missing, "broken relative documentation links:\n" + "\n".join(missing)


def test_documentation_has_no_old_monorepo_links() -> None:
    old_location = "github.com/marcelpetrick/codingWithGPT/tree/master/AgentWhileTrue"
    offenders = [
        document.name
        for document in _markdown_files()
        if old_location in document.read_text(encoding="utf-8")
    ]
    assert not offenders, f"old monorepo links remain in: {', '.join(offenders)}"
