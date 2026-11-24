"""Six proof kinds returning PROVEN, REFUTED, or UNRUNNABLE when the check
cannot be made here. `command` and `repro` are an argv list allowlisted by
name: no shell.
"""

from __future__ import annotations

import fnmatch
import json as jsonlib
import re
import subprocess
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from .domain.changes import change_lines
from .domain.adjudication import ProofOutcome
from .domain.findings import State
from .sandbox import argv as sandbox_argv
from .domain.vocabulary import PROOF_KINDS

SKIP_DIRS = frozenset({".git", ".council", ".venv", "__pycache__", "node_modules", ".mypy_cache"})


@dataclass(frozen=True, slots=True)
class ProofContext:
    repo: Path
    allow: frozenset[str]
    diff: str | None = None
    timeout: int = 120
    sandbox: bool = True


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


def _glob_list(params: Mapping[str, Any], key: str) -> tuple[str, ...]:
    value = params.get(key, [])
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise _BadParams(f"params.{key}: expected a list of globs")
    return tuple(value)


def _scope_globs(params: Mapping[str, Any]) -> tuple[str, ...]:
    """`within` narrows an absence claim to the paths it is about.

    Without it an absence claim is repository-wide ("nothing else references
    this"), and an unrelated hit anywhere refutes it: a module-level claim,
    settled by a file that has nothing to do with it. The globs are validated
    like a review scope, so a path that leaves the repository is a parameter
    error rather than a scope that silently matches nothing.
    """
    within = _glob_list(params, "within")
    for glob in within:
        if not glob or glob.startswith("/") or "\\" in glob or ".." in glob.split("/"):
            raise _BadParams(
                f"params.within: {glob!r} must be a repository-relative POSIX glob")
    return within


def _path_param(ctx: ProofContext, params: Mapping[str, Any], key: str = "path") -> Path:
    raw = _str_param(params, key)
    root = ctx.repo.resolve()
    target = (root / raw).resolve()
    if not target.is_relative_to(root):
        raise _BadParams(f"params.{key}: {raw!r} leaves the repository")
    try:
        regular = target.is_file()
    except OSError as exc:
        raise _BadParams(f"params.{key}: {raw!r} cannot be read: {exc}") from exc
    if not regular:
        raise _BadParams(f"params.{key}: {raw!r} is not a regular file")
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
    exclude = _glob_list(params, "exclude")
    within = _scope_globs(params)

    try:
        paths = _walk(ctx.repo)
    except OSError as exc:
        return _cannot(f"the repository cannot be walked: {exc}")
    considered = 0
    for path in paths:
        rel = path.relative_to(ctx.repo).as_posix()
        if within and not any(fnmatch.fnmatch(rel, glob) for glob in within):
            continue
        if any(fnmatch.fnmatch(rel, glob) for glob in exclude):
            continue
        considered += 1
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        found = rx.search(text)
        if found is not None:
            line = text.count("\n", 0, found.start()) + 1
            return _failed(f"/{pattern}/ is present at {rel}:{line}")
    if within and considered == 0:
        # An absence proved over nothing is not an absence. This is the same
        # rule as a review scope that removes every file: refused, not passed.
        return _cannot(f"no readable file matches {', '.join(within)}: nothing was searched")
    scope = f" under {', '.join(within)}" if within else ""
    return _held(f"/{pattern}/ appears in no file{scope}")


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
    # A reviewer quoting a line omits the column it starts in: the indentation is
    # the file's layout, not part of what the line says. Nothing else is
    # normalised — case, internal spacing and trailing text must still match,
    # because the proof is about the text, and a looser rule would prove claims
    # the line does not support.
    if actual.strip() == expected.strip():
        return _held(f"{path.name}:{line} says {actual.strip()!r}")
    wanted = expected.strip()
    hits: list[int] = []
    for index, candidate in enumerate(lines):
        if candidate.strip() == wanted:
            hits.append(index + 1)
            if len(hits) == 3:
                break
    if hits:
        where = ", ".join(str(item) for item in hits)
        return _cannot(
            f"{path.name}:{line} does not contain the quote; the same text occurs at line {where}: "
            "the cited line is stale")
    return _failed(f"{path.name}:{line} says {actual.strip()!r}, not {wanted!r}")


def _argv_param(params: Mapping[str, Any]) -> list[str]:
    argv = params.get("argv")
    if not isinstance(argv, list) or not argv or not all(
            isinstance(item, str) and item for item in argv):
        raise _BadParams("params.argv: expected a non-empty list of strings")
    return argv


#: A proof whose command could not load its own dependency did not test the
#: claim. Two shapes occur, and both begin the line: the exception itself, and
#: the interpreter's own diagnostic. `-m` adds "Error while finding module
#: specification" to the second.
#:
#: The line must *start* with one of them. A test that prints the exception text
#: A diagnostic is an interpreter line, so it is classified at a line start.
#:
#: Stderr is read as it is. Stdout is read only for a line carrying pytest's own
#: `E   ` report marker: that is pytest reporting an exception, not a proof
#: printing. A bare stdout line is never a diagnostic, so a proof that prints
#: without a trailing newline cannot glue itself onto one, and a test asserting
#: on a quoted exception stays a test result.
_DEPENDENCY_LINE = re.compile(
    r"^(?:ModuleNotFoundError:|(?:[^:\s]*/)?python[0-9.]*: )")
#: The only thing an import failure says. `-m` wraps it in a "finding module
#: specification" clause, but a bug inside an installed package reports that
#: same clause without any missing import, so the clause is not a signal.
_DEPENDENCY_TEXT = ("No module named",)


def _missing_dependency(stdout: str, stderr: str) -> str | None:
    """The import diagnostic, if the proof environment lacked a dependency.

    Stderr is classified at a line start, which is where an interpreter writes
    it. Stdout is classified only when a line carries pytest's own `E   ` report
    marker *and* starts with the diagnostic after it: that is pytest reporting
    an exception, not a proof quoting one. Anything else on stdout is the
    proof's own text, so a proof that prints without a trailing newline cannot
    glue itself onto a diagnostic, and an assertion that quotes one is ignored.
    """
    def diagnostic(line: str) -> str | None:
        if not _DEPENDENCY_LINE.match(line):
            return None
        if any(part in line for part in _DEPENDENCY_TEXT):
            return line
        return None

    for line in stderr.splitlines():
        found = diagnostic(line.strip())
        if found is not None:
            return found
    for line in stdout.splitlines():
        if not re.match(r"^E {2,}", line):
            continue
        found = diagnostic(re.sub(r"^E {2,}", "", line).strip())
        if found is not None:
            return found
    return None


def _normalise_argv(argv: list[str], ctx: ProofContext) -> list[str]:
    if argv[0] == "python" and "python" not in ctx.allow and "python3" in ctx.allow:
        return ["python3", *argv[1:]]
    return argv


def _dependency_failure(ran: _Ran) -> ProofOutcome | None:
    """Did the command fail because the proof environment lacked a dependency?

    `contains` decides whether a failure is the claimed one, so a repro that
    names the exact import error is evidence even when the module is missing:
    the finding is *about* that absence. Only an unnamed failure is ambiguous,
    and only an unnamed one is deferred to the classifier.
    """
    if ran.returncode == 0:
        return None
    found = _missing_dependency(ran.stdout, ran.stderr)
    if found is not None:
        return _cannot(f"the proof could not import a dependency: {found}")
    return None


@dataclass(frozen=True, slots=True)
class _Ran:
    """A command that ran: its exit code, all its output, and its stderr.

    `output` is stdout followed by stderr, which is what a `contains` expectation
    matches against: a reviewer names the failure, not the stream it came on.
    `stderr` is kept apart because a diagnostic is classified there, so a proof
    that prints without a newline cannot disguise one.
    """

    returncode: int
    output: str
    stdout: str = ""
    stderr: str = ""


def _attempt(argv: list[str], ctx: ProofContext) -> _Ran | ProofOutcome:
    """Run an allowlisted argv in the sandbox.

    A `ProofOutcome` return means "this could not be run here" — never "the
    claim is false". Both command-shaped kinds share it, so a new kind cannot
    invent a weaker way to start a process: same allowlist, same overlay, same
    refusals.
    """
    argv = _normalise_argv(argv, ctx)
    binary = argv[0]
    if "/" in binary or "\\" in binary:
        return _cannot(f"{binary!r} is a path; a proof names an allowlisted executable, not a path")
    if binary not in ctx.allow:
        return _cannot(f"{binary!r} is not on [proofs].allow")

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

    stderr = proc.stderr or ""
    if proc.returncode != 0 and stderr.startswith("bwrap:"):
        first = stderr.strip().splitlines()[0]
        return _cannot(f"the sandbox could not start: {first}")

    if proc.returncode != 0 and "read-only file system" in stderr.lower():
        tail = stderr.strip().splitlines()
        return _cannot("the command needed to write outside the repository and /tmp, "
                       f"which the sandbox keeps read-only: {tail[-1] if tail else 'EROFS'}")

    return _Ran(proc.returncode, (proc.stdout or "") + stderr,
                proc.stdout or "", stderr)


def proof_command(params: Mapping[str, Any], ctx: ProofContext) -> ProofOutcome:
    argv = _argv_param(params)
    expectation = params.get("expect", {})
    if not isinstance(expectation, dict):
        raise _BadParams("params.expect: expected an object")
    mode = expectation.get("exit", "zero")
    if mode not in ("zero", "nonzero"):
        raise _BadParams("params.expect.exit: expected 'zero' or 'nonzero'")

    ran = _attempt(argv, ctx)
    if isinstance(ran, ProofOutcome):
        return ran
    dependency = _dependency_failure(ran)
    if dependency is not None:
        return dependency
    passed = ran.returncode == 0 if mode == "zero" else ran.returncode != 0
    if passed:
        return _held(f"{' '.join(argv)} exited {ran.returncode} (expected {mode})")
    return _failed(f"{' '.join(argv)} exited {ran.returncode} (expected {mode})")


def proof_repro(params: Mapping[str, Any], ctx: ProofContext) -> ProofOutcome:
    """The defect reproduces when the command fails.

    A `command` proof asserts an expectation the reviewer chose; a `repro` proof
    asserts one thing only — that the defect can be demonstrated here. Its pass
    condition is a non-zero exit, which is why it is a kind of its own rather
    than `command` with `expect.exit = "nonzero"`: the finding's meaning decides,
    not the reviewer's optimism. `contains` pins the failure to the one claimed,
    so a command that fails for an unrelated reason does not settle it.
    """
    argv = _argv_param(params)
    contains = params.get("contains")
    if contains is not None and (not isinstance(contains, str) or not contains):
        raise _BadParams("params.contains: expected a non-empty string")

    ran = _attempt(argv, ctx)
    if isinstance(ran, ProofOutcome):
        return ran
    if ran.returncode == 0:
        return _failed(f"{' '.join(argv)} exited 0: the defect did not reproduce")
    diagnostic = _missing_dependency(ran.stdout, ran.stderr)
    if diagnostic is not None:
        # A missing import means the check could not run. It is evidence only
        # when the finding is *about* that absence: `contains` must name the
        # diagnostic itself. A match anywhere else in the output — a progress
        # line, say — says nothing about why the command stopped.
        if contains is not None and contains in diagnostic:
            return _held(f"{' '.join(argv)} exited {ran.returncode}, "
                         "reproducing the missing import the finding names")
        return _cannot(f"the proof could not import a dependency: {diagnostic}")
    if contains is not None:
        if contains not in ran.output:
            return _failed(f"{' '.join(argv)} exited {ran.returncode} without "
                           f"{contains!r}: not the failure the finding claims")
        return _held(f"{' '.join(argv)} exited {ran.returncode}, reproducing the defect")
    return _held(f"{' '.join(argv)} exited {ran.returncode}, reproducing the defect")


def _pointer(document: Any, pointer: str) -> Any:
    if pointer == "":
        return document
    if not pointer.startswith("/"):
        raise KeyError(pointer)
    current = document
    for raw in pointer[1:].split("/"):
        part = raw.replace("~1", "/").replace("~0", "~")
        if isinstance(current, list):
            if re.fullmatch(r"(0|[1-9][0-9]*)", part) is None:
                raise KeyError(part)
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
    "repro": proof_repro,
    "json": proof_json,
    "diff": proof_diff,
}

#: The parser may accept a kind only if this module can actually execute it.
assert set(EXECUTORS) == set(PROOF_KINDS), "proof kinds and executors disagree"


def run_proof(kind: str, params: Mapping[str, Any], ctx: ProofContext) -> ProofOutcome:
    """Settle one proof. Malformed params cannot run, so they are `UNRUNNABLE`.

    The kind travels with the outcome. Whether a finding was demonstrated by
    running something or only by quoting a line is part of what the verdict is
    allowed to depend on, so it cannot be reconstructed later from the params.
    """
    executor = EXECUTORS.get(kind)
    if executor is None:
        return replace(_cannot(f"{kind!r} is not a proof kind"), kind=kind)
    try:
        outcome = executor(params, ctx)
    except _BadParams as exc:
        outcome = _cannot(str(exc))
    except Exception as exc:  # noqa: BLE001 - untrusted params must not crash the run
        outcome = _cannot(f"the proof crashed: {type(exc).__name__}: {exc}")
    return replace(outcome, kind=kind)
