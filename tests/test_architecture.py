"""The decision kernel is pure; every module that acts is named.

A decision must be reproducible from its inputs alone. The pure list is the
domain kernel: answering a question may not read, write, spawn, wait or read
the environment. The adapters are the effect shell; a module that acts and is
not named here fails the gate instead of silently widening the boundary.

The module file is resolved through `importlib`, not a hardcoded `src/` path:
a test that scans the checkout keeps inspecting the unmutated tree when the
suite runs against a copy.
"""

from __future__ import annotations

import ast
import importlib
from pathlib import Path

import pytest

#: The decision kernel: everything under `council.domain`. Answering a question
#: there may not read, write, spawn, wait or touch the environment. The list is
#: the package, not a selection from it — a pure module that lives outside is a
#: module the next reader has to classify by hand.
PURE = (
    "domain.__init__",
    "domain.adjudication",
    "domain.baseline",
    "domain.changes",
    "domain.config",
    "domain.context",
    "domain.findings",
    "domain.location",
    "domain.merge",
    "domain.prompt",
    "domain.run_id",
    "domain.sandbox",
    "domain.sarif",
    "domain.schema",
    "domain.scope",
    "domain.text",
    "domain.verdict",
    "domain.vocabulary",
)

#: The effect shell. Each of these may read, write, spawn or wait.
ADAPTERS = frozenset({
    "__main__",
    "adjudicate",
    "base",
    "baseline",
    "claims",
    "cli",
    "cli_output",
    "cli_parser",
    "config",
    "doctor",
    "paths",
    "planning",
    "prepare",
    "pr",
    "proofs",
    "reference",
    "repo",
    "request",
    "run",
    "runstore",
    "runner",
    "sample",
    "sampling",
    "sandbox",
    "skill_install",
    "version",
    "agents.__init__",
    "agents.base",
    "agents.hermes",
})

FORBIDDEN_IMPORTS = frozenset({
    "argparse", "ftplib", "http", "importlib", "os", "pathlib", "platform",
    "random", "shutil", "socket", "ssl", "subprocess", "sys", "tempfile",
    "time", "urllib",
})
#: Method names that read or change the world. `replace`/`remove`/`read`/
#: `write`/`flush`/`close` are omitted: they are also ordinary string, list,
#: callback and local-helper names and would produce false positives. Direct
#: file I/O is still caught by `open`, `*_text`, `*_bytes`, `mkdir`, `stat`, etc.
FORBIDDEN_CALLS = frozenset({
    "Popen", "chmod", "eval", "exec", "exists", "getcwd", "getenv", "glob",
    "input", "is_dir", "is_file", "is_symlink", "iterdir", "listdir", "mkdir",
    "monotonic", "open", "print", "read_bytes", "read_text", "rename",
    "resolve", "rglob", "rmdir", "run", "scandir", "sleep", "stat", "system",
    "touch", "unlink", "urlopen", "which", "write_bytes", "write_text",
})
#: Importing `pathlib` is allowed only for constructing a path in the pure
#: sandbox argv builder; its methods are still checked by name.
PATHLIB_ALLOWED = {"domain.sandbox"}


def tree(module: str) -> ast.Module:
    loaded = importlib.import_module(f"council.{module}")
    return ast.parse(Path(loaded.__file__ or "").read_text(encoding="utf-8"))


def imports(node: ast.Module) -> set[str]:
    names: set[str] = set()
    for item in ast.walk(node):
        if isinstance(item, ast.Import):
            names.update(alias.name.split(".")[0] for alias in item.names)
        elif isinstance(item, ast.ImportFrom) and item.module:
            names.add(item.module.split(".")[0])
    return names


def calls(node: ast.Module) -> set[str]:
    names: set[str] = set()
    for item in ast.walk(node):
        if not isinstance(item, ast.Call):
            continue
        func = item.func
        if isinstance(func, ast.Name):
            names.add(func.id)
        elif isinstance(func, ast.Attribute):
            names.add(func.attr)
    return names


@pytest.mark.parametrize("module", PURE)
def test_a_pure_module_imports_nothing_that_acts(module: str) -> None:
    imported = imports(tree(module))
    forbidden = imported & FORBIDDEN_IMPORTS
    if module in PATHLIB_ALLOWED:
        forbidden -= {"pathlib"}
    assert not forbidden, f"{module} imports {sorted(forbidden)}"


@pytest.mark.parametrize("module", PURE)
def test_a_pure_module_calls_nothing_that_acts(module: str) -> None:
    acted = calls(tree(module)) & FORBIDDEN_CALLS
    assert not acted, f"{module} calls {sorted(acted)}"


@pytest.mark.parametrize("module", PURE)
def test_a_pure_module_does_not_import_an_adapter(module: str) -> None:
    imported = imports(tree(module))
    adapters = imported & ADAPTERS
    assert not adapters, f"{module} imports adapter(s) {sorted(adapters)}"


def test_every_module_that_acts_is_named_as_an_adapter() -> None:
    """A new impure module cannot join the package without an explicit classification."""
    package = Path(importlib.import_module("council").__file__ or "").parent
    modules = ["__init__"]
    modules += sorted(path.stem for path in package.glob("*.py")
                      if path.stem not in {"__init__", "__main__"})
    modules += ["domain.__init__"]
    modules += [f"domain.{path.stem}" for path in (package / "domain").glob("*.py")
                if path.stem != "__init__"]
    modules += [f"agents.{path.stem}" for path in (package / "agents").glob("*.py")
                if path.stem != "__init__"]
    modules.append("agents.__init__")
    acted: list[str] = []
    for module in modules:
        node = tree(module)
        imported = imports(node) & FORBIDDEN_IMPORTS
        if module in PATHLIB_ALLOWED:
            imported -= {"pathlib"}
        if imported or (calls(node) & FORBIDDEN_CALLS):
            acted.append(module)
    unclassified = sorted(set(acted) - ADAPTERS)
    assert not unclassified, f"effectful modules not named as adapters: {unclassified}"


def test_every_module_is_either_kernel_or_adapter() -> None:
    """Two homes. A module in neither is a boundary nobody declared."""
    package = Path(importlib.import_module("council").__file__ or "").parent
    kernel = {f"domain.{path.stem}" for path in (package / "domain").glob("*.py")}
    kernel |= {"domain.__init__", "__init__"}
    modules = {path.stem for path in package.glob("*.py")} | {
        f"domain.{path.stem}" for path in (package / "domain").glob("*.py")} | {
        f"agents.{path.stem}" for path in (package / "agents").glob("*.py")}
    stray = sorted(modules - kernel - ADAPTERS)
    assert not stray, f"modules that are neither kernel nor named adapter: {stray}"


def test_the_package_import_reads_no_metadata() -> None:
    """`council.__version__` is a constant; the installed lookup is an adapter."""
    assert "importlib" not in imports(tree("__init__"))
