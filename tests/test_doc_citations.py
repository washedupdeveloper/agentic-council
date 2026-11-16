"""A current-state document may not cite a test that is not there."""

from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
#: History records what was true then: an ADR may name a test that has since gone.
HISTORY = re.compile(r"(^M\d+\.md$|^CHANGELOG\.md$|^UNTANGLE.*\.md$|^CLAIMS\.md$)")
CITE = re.compile(r"`(test_[a-z0-9_]+)`")


def known_tests() -> set[str]:
    found: set[str] = set()
    for path in (ROOT / "tests").glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                found.add(node.name)
    return found


def current_documents() -> list[Path]:
    found = [path for path in sorted((ROOT / "docs").glob("*.md"))
             if not HISTORY.search(path.name)]
    return found + [ROOT / "README.md", ROOT / "GLOSSARY.md"]


def test_every_current_document_cites_a_test_that_exists() -> None:
    existing = known_tests()
    cited = 0
    missing: list[str] = []
    for path in current_documents():
        for name in CITE.findall(path.read_text(encoding="utf-8")):
            cited += 1
            if name not in existing:
                missing.append(f"{path.relative_to(ROOT)} -> {name}")
    assert cited > 50, f"only {cited} citations found: the pattern or the documents changed"
    assert not missing, "documents cite tests that do not exist: " + "; ".join(missing)
