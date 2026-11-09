"""The decision path is pure; the modules that act are enumerated.

`parse`, `merge`, `judge` and `render` decide, and a decision must be
reproducible from its inputs alone. A module on the pure list may not import or
call anything that reads, writes, spawns or waits; the effect shell is the
short list of modules that may, and each of those is named in the README.
"""

from __future__ import annotations

import ast
import importlib
from pathlib import Path

import pytest

#: The decision path. Everything here answers a question without touching the world.
PURE = ("findings", "verdict", "merge", "schema", "prompt", "paths", "changes", "context")

FORBIDDEN_IMPORTS = frozenset({
    "subprocess", "urllib", "socket", "os", "time", "random", "shutil", "tempfile", "sys",
})
FORBIDDEN_CALLS = frozenset({
    "open", "write_text", "write_bytes", "mkdir", "unlink", "rmdir", "rename",
    "run", "Popen", "system", "urlopen",
})


def tree(module: str) -> ast.Module:
    """The module that is actually imported, so a mutated tree is inspected too."""
    loaded = importlib.import_module(f"council.{module}")
    return ast.parse(Path(loaded.__file__ or "").read_text(encoding="utf-8"))


@pytest.mark.parametrize("module", PURE)
def test_a_pure_module_imports_nothing_that_acts(module: str) -> None:
    imported: set[str] = set()
    for node in ast.walk(tree(module)):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    forbidden = imported & FORBIDDEN_IMPORTS
    assert not forbidden, f"{module} imports {sorted(forbidden)}"


@pytest.mark.parametrize("module", PURE)
def test_a_pure_module_calls_nothing_that_acts(module: str) -> None:
    called: set[str] = set()
    for node in ast.walk(tree(module)):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name):
            name = func.id
        elif isinstance(func, ast.Attribute):
            name = func.attr
        else:
            continue
        if name in FORBIDDEN_CALLS:
            called.add(name)
    assert not called, f"{module} calls {sorted(called)}"
