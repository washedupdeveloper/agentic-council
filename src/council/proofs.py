"""Seven proof kinds returning PROVEN, REFUTED, or UNRUNNABLE when the check
cannot be made here. `command` is an argv list allowlisted by name: no shell."""

from __future__ import annotations

import fnmatch
import json as jsonlib
import re
import subprocess
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

from .findings import State

SKIP_DIRS = frozenset({".git", ".council", ".venv", "__pycache__", "node_modules", ".mypy_cache"})


@dataclass(frozen=True, slots=True)
class ProofContext:
    repo: Path
    allow: frozenset[str]
    diff: str | None = None
    timeout: int = 120


@dataclass(frozen=True, slots=True)
class ProofOutcome:
    state: State
    detail: str


def _held(detail: str) -> ProofOutcome:
    return ProofOutcome(State.PROVEN, detail)


def _failed(detail: str) -> ProofOutcome:
    return ProofOutcome(State.REFUTED, detail)


def _cannot(detail: str) -> ProofOutcome:
    return ProofOutcome(State.UNRUNNABLE, detail)


class _BadParams(ValueError):
    pass


def _str_param(params: Mapping[str, Any], key: str) -> str:
    value = params.get(key)
    if not isinstance(value, str) or not value:
        raise _BadParams(f"params.{key}: expected a non-empty string")
    return value


def _int_param(params: Mapping[str, Any], key: str) -> int:
    value = params.get(key)
    if not isinstance(value, int) or isinstance(value, bool):
        raise _BadParams(f"params.{key}: expected an integer")
    return value


def _path_param(ctx: ProofContext, params: Mapping[str, Any], key: str = "path") -> Path:
    raw = _str_param(params, key)
    root = ctx.repo.resolve()
    target = (root / raw).resolve()
    if not target.is_relative_to(root):
        raise _BadParams(f"params.{key}: {raw!r} leaves the repository")
    return target


def _walk(root: Path) -> list[Path]:
    out: list[Path] = []
    for path in root.rglob("*"):
        if any(part in SKIP_DIRS for part in path.relative_to(root).parts):
            continue
        if path.is_file():
            out.append(path)
    return sorted(out)


def proof_absent(params: Mapping[str, Any], ctx: ProofContext) -> ProofOutcome:
    pattern = _str_param(params, "pattern")
    try:
        rx = re.compile(pattern)
    except re.error as exc:
        return _cannot(f"params.pattern is not a valid regex: {exc}")
    exclude = params.get("exclude", [])
    if not isinstance(exclude, list) or not all(isinstance(x, str) for x in exclude):
        raise _BadParams("params.exclude: expected a list of globs")

    for path in _walk(ctx.repo):
        rel = path.relative_to(ctx.repo).as_posix()
        if any(fnmatch.fnmatch(rel, glob) for glob in exclude):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        found = rx.search(text)
        if found is not None:
            line = text.count("\n", 0, found.start()) + 1
            return _failed(f"/{pattern}/ is present at {rel}:{line}")
    return _held(f"/{pattern}/ appears in no file")


def proof_present(params: Mapping[str, Any], ctx: ProofContext) -> ProofOutcome:
    path = _path_param(ctx, params)
    line = _int_param(params, "line")
    expected = _str_param(params, "text")
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as exc:
        return _cannot(f"{path.name} cannot be read: {exc}")
    if not 1 <= line <= len(lines):
        return _cannot(f"{path.name} has no line {line}")
    actual = lines[line - 1]
    if actual == expected:
        return _held(f"{path.name}:{line} says {expected!r}")
    return _failed(f"{path.name}:{line} says {actual!r}")


def proof_command(params: Mapping[str, Any], ctx: ProofContext) -> ProofOutcome:
    argv = params.get("argv")
    if not isinstance(argv, list) or not argv or not all(isinstance(a, str) and a for a in argv):
        raise _BadParams("params.argv: expected a non-empty list of strings")
    binary = argv[0]
    if "/" in binary or "\\" in binary:
        return _cannot(f"{binary!r} is a path; a proof names an allowlisted executable, not a path")
    if binary not in ctx.allow:
        return _cannot(f"{binary!r} is not on [proofs].allow")

    expectation = params.get("expect", {})
    if not isinstance(expectation, dict):
        raise _BadParams("params.expect: expected an object")
    mode = expectation.get("exit", "zero")
    if mode not in ("zero", "nonzero"):
        raise _BadParams("params.expect.exit: expected 'zero' or 'nonzero'")

    try:
        proc = subprocess.run(
            argv, cwd=ctx.repo, capture_output=True, text=True, timeout=ctx.timeout, check=False
        )
    except FileNotFoundError:
        return _cannot(f"{binary!r} is not installed on this host")
    except subprocess.TimeoutExpired:
        return _cannot(f"{' '.join(argv)} did not finish within {ctx.timeout}s")
    except OSError as exc:
        return _cannot(f"{binary!r} could not be started: {exc}")

    passed = proc.returncode == 0 if mode == "zero" else proc.returncode != 0
    if passed:
        return _held(f"{' '.join(argv)} exited {proc.returncode} (expected {mode})")
    return _failed(f"{' '.join(argv)} exited {proc.returncode} (expected {mode})")


def _pointer(document: Any, pointer: str) -> Any:
    if pointer in ("", "/"):
        return document
    current = document
    for raw in pointer.lstrip("/").split("/"):
        part = raw.replace("~1", "/").replace("~0", "~")
        if isinstance(current, list):
            current = current[int(part)]
        elif isinstance(current, dict):
            current = current[part]
        else:
            raise KeyError(part)
    return current


def _same(left: Any, right: Any) -> bool:
    """Equality that does not let True pass for 1."""
    if isinstance(left, bool) != isinstance(right, bool):
        return False
    return bool(left == right)


def proof_json(params: Mapping[str, Any], ctx: ProofContext) -> ProofOutcome:
    path = _path_param(ctx, params)
    pointer = _str_param(params, "pointer")
    if "equals" not in params:
        raise _BadParams("params.equals: missing")
    try:
        document = jsonlib.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, jsonlib.JSONDecodeError) as exc:
        return _cannot(f"{path.name} cannot be read as JSON: {exc}")
    try:
        value = _pointer(document, pointer)
    except (KeyError, IndexError, ValueError):
        return _cannot(f"{path.name} has nothing at {pointer}")
    if _same(value, params["equals"]):
        return _held(f"{path.name}{pointer} is {value!r}")
    return _failed(f"{path.name}{pointer} is {value!r}, not {params['equals']!r}")


def proof_http(params: Mapping[str, Any], ctx: ProofContext) -> ProofOutcome:
    url = _str_param(params, "url")
    expected = _int_param(params, "expect_status")
    request = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=min(ctx.timeout, 30)) as response:
            status = response.status
    except urllib.error.HTTPError as exc:
        status = exc.code
    except (urllib.error.URLError, OSError) as exc:
        return _cannot(f"{url} could not be reached: {exc}")
    if status == expected:
        return _held(f"GET {url} returned {status}")
    return _failed(f"GET {url} returned {status}, not {expected}")


def proof_dom(params: Mapping[str, Any], ctx: ProofContext) -> ProofOutcome:
    _str_param(params, "selector")
    return _cannot("no browser executor is built yet: the dom proof cannot be made on this host")


def change_lines(diff: str) -> dict[str, tuple[set[int], set[int]]]:
    """path -> (line numbers added in the new file, line numbers removed from the old).

    Line numbers come from each hunk header, so a change with several hunks is
    read hunk by hunk rather than only where the last one ended.
    """
    changes: dict[str, tuple[set[int], set[int]]] = {}
    path: str | None = None
    old_line = new_line = 0
    for raw in diff.splitlines():
        if raw.startswith("+++ "):
            target = raw[4:].strip()
            path = None if target == "/dev/null" else (target[2:] if target.startswith("b/") else target)
            continue
        if raw.startswith("--- ") or raw.startswith("diff --git") or raw.startswith("index "):
            continue
        header = re.match(r"^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@", raw)
        if header is not None:
            old_line, new_line = int(header.group(1)), int(header.group(2))
            continue
        if path is None:
            continue
        added, removed = changes.setdefault(path, (set(), set()))
        if raw.startswith("+"):
            added.add(new_line)
            new_line += 1
        elif raw.startswith("-"):
            removed.add(old_line)
            old_line += 1
        elif raw.startswith(" "):
            old_line += 1
            new_line += 1
    return changes


def proof_diff(params: Mapping[str, Any], ctx: ProofContext) -> ProofOutcome:
    if ctx.diff is None:
        return _cannot("no diff was supplied to this run")
    path = _str_param(params, "path")
    line = _int_param(params, "line")
    mode = _str_param(params, "mode")
    if mode not in ("added", "removed"):
        raise _BadParams("params.mode: expected 'added' or 'removed'")
    changes = change_lines(ctx.diff)
    if path not in changes:
        return _failed(f"{path} does not appear in the diff")
    added, removed = changes[path]
    wanted = added if mode == "added" else removed
    if line in wanted:
        return _held(f"{path}:{line} is {mode} by this change")
    return _failed(f"{path}:{line} is not {mode} by this change")


EXECUTORS: dict[str, Callable[[Mapping[str, Any], ProofContext], ProofOutcome]] = {
    "absent": proof_absent,
    "present": proof_present,
    "command": proof_command,
    "json": proof_json,
    "http": proof_http,
    "dom": proof_dom,
    "diff": proof_diff,
}


def run_proof(kind: str, params: Mapping[str, Any], ctx: ProofContext) -> ProofOutcome:
    """Settle one proof. Malformed params cannot run, so they are `UNRUNNABLE`."""
    executor = EXECUTORS.get(kind)
    if executor is None:
        return _cannot(f"{kind!r} is not a proof kind")
    try:
        return executor(params, ctx)
    except _BadParams as exc:
        return _cannot(str(exc))