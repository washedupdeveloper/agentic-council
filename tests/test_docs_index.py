"""The index is a binding, not a table of contents somebody maintains by hand."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INDEX = ROOT / "docs" / "README.md"
LINK = re.compile(r"\]\(([^)\s]+)\)")
#: Fixture trees are other repositories' files; they are not this project's docs.
SKIP = {"fixtures"}


def documents() -> list[Path]:
    found: list[Path] = []
    for path in ROOT.rglob("*.md"):
        parts = path.relative_to(ROOT).parts
        if set(parts) & SKIP or any(part.startswith(".") for part in parts):
            continue
        found.append(path)
    return sorted(found)


def links() -> list[tuple[str, Path]]:
    found: list[tuple[str, Path]] = []
    for target in LINK.findall(INDEX.read_text(encoding="utf-8")):
        if target.startswith(("http://", "https://", "mailto:")):
            continue
        found.append((target, (INDEX.parent / target.split("#", 1)[0]).resolve()))
    return found


def test_every_document_is_linked_from_the_index() -> None:
    listed = {path for _, path in links()}
    missing = [path.relative_to(ROOT).as_posix() for path in documents()
               if path != INDEX and path not in listed]
    assert not missing, "unindexed document(s): " + ", ".join(missing)


def test_every_link_on_the_index_resolves() -> None:
    broken = [target for target, path in links() if not path.exists()]
    assert not broken, "broken link(s): " + ", ".join(broken)


def test_the_index_lists_more_than_a_handful_of_documents() -> None:
    """A page that indexes nothing would pass both checks above."""
    assert len([path for path in documents() if path != INDEX]) > 20
