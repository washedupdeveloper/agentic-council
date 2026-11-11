"""Six proof kinds returning PROVEN, REFUTED, or UNRUNNABLE when the check
cannot be made here. `command` is an argv list allowlisted by name: no shell."""

from __future__ import annotations

import fnmatch
import json as jsonlib
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

from .changes import change_lines
from .findings import State
from .sandbox import argv as sandbox_argv

SKIP_DIRS = frozenset({".git", ".council", ".venv", "__pycache__", "node_modules", ".mypy_cache"})


@dataclass(frozen=True, slots=True)
class ProofContext:
    repo: Path
    allow: frozenset[str]
    diff: str | None = None
    timeout: int = 120
    sandbox: bool = True


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
        if path.is_symlink():
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

    try:
        paths = _walk(ctx.repo)
    except OSError as exc:
        return _cannot(f"the repository cannot be walked: {exc}")
    for path in paths:
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

    command = argv
    if ctx.sandbox:
        wrapped = sandbox_argv(argv, ctx.repo)
        if wrapped is None:
            return _cannot("bwrap is not installed: command proofs run in a sandbox "
                           "(install bubblewrap, or set [proofs] sandbox = false)")
        command = wrapped

    try:
        proc = subprocess.run(
            command, cwd=ctx.repo, capture_output=True, text=True,
            errors="replace", timeout=ctx.timeout, check=False
        )
    except FileNotFoundError:
        return _cannot(f"{binary!r} is not installed on this host")
    except subprocess.TimeoutExpired:
        return _cannot(f"{' '.join(argv)} did not finish within {ctx.timeout}s")
    except (OSError, ValueError) as exc:
        return _cannot(f"{binary!r} could not be started: {exc}")

    if proc.returncode != 0 and (proc.stderr or "").startswith("bwrap:"):
        first = (proc.stderr or "").strip().splitlines()[0]
        return _cannot(f"the sandbox could not start: {first}")

    if proc.returncode != 0 and "read-only file system" in (proc.stderr or "").lower():
        tail = (proc.stderr or "").strip().splitlines()
        return _cannot("the command needed to write outside the repository and /tmp, "
                       f"which the sandbox keeps read-only: {tail[-1] if tail else 'EROFS'}")

    passed = proc.returncode == 0 if mode == "zero" else proc.returncode != 0
    if passed:
        return _held(f"{' '.join(argv)} exited {proc.returncode} (expected {mode})")
    return _failed(f"{' '.join(argv)} exited {proc.returncode} (expected {mode})")


def _pointer(document: Any, pointer: str) -> Any:
    if pointer == "":
        return document
    if not pointer.startswith("/"):
        raise KeyError(pointer)
    current = document
    for raw in pointer[1:].split("/"):
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
    except Exception as exc:  # noqa: BLE001 - untrusted params must not crash the run
        return _cannot(f"the proof crashed: {type(exc).__name__}: {exc}")
