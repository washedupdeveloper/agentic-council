"""Can this machine run a review? Measure it before a review depends on it."""

from __future__ import annotations

import os
import shutil
import time
import tomllib
from dataclasses import dataclass
from pathlib import Path

from .domain.text import sanitize
from .sample import Runner
from .version import SOURCE_VERSION, current_version

PROBE = "Reply with the single word: ok"
OK = "ok"
WARN = "warn"
FAIL = "fail"


@dataclass(frozen=True, slots=True)
class Check:
    """One thing a review needs, and what this machine says about it."""

    name: str
    status: str
    detail: str

    def line(self) -> str:
        return f"{self.status:<4}  {self.name:<8}  {sanitize(self.detail)}"


def check_git() -> Check:
    path = shutil.which("git")
    return Check("git", OK, path) if path else Check("git", FAIL, "git is not on PATH")


def check_reviewer(binary: str) -> Check:
    try:
        path = shutil.which(binary)
        if path is None:
            candidate = Path(binary)
            if candidate.is_file() and os.access(candidate, os.X_OK):
                path = str(candidate)
    except (OSError, ValueError) as exc:
        return Check("reviewer", FAIL, f"{binary}: {exc}")
    if path:
        return Check("reviewer", OK, path)
    return Check("reviewer", FAIL, f"{binary} is not on PATH")


def check_sandbox() -> Check:
    path = shutil.which("bwrap")
    if path:
        return Check("bwrap", OK, path)
    return Check("bwrap", WARN, "not on PATH: command proofs will be UNRUNNABLE")


def check_agent(name: str, runner: Runner, probe_timeout: int) -> Check:
    """Ask the selected agent a question it must answer quickly."""
    started = time.monotonic()
    try:
        answer = runner(PROBE)
    except Exception as exc:  # noqa: BLE001 - every failure is the finding here
        return Check("agent", FAIL, f"{name}: {type(exc).__name__}: {exc}")
    seconds = time.monotonic() - started
    if not isinstance(answer, str) or not answer.strip():
        return Check("agent", FAIL, f"{name}: the probe returned nothing")
    return Check("agent", OK,
                 f"{name} answered in {seconds:.1f}s (probe limit {probe_timeout}s)")


def check_source(source: Path | None) -> Check | None:
    """Compare the installed version with the source tree's declared version."""
    if source is None:
        return None
    pyproject = source / "pyproject.toml"
    try:
        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
        source_version = data["project"]["version"]
    except (OSError, KeyError, TypeError, tomllib.TOMLDecodeError) as exc:
        return Check("source", FAIL, f"{source}: cannot read project.version ({exc})")
    installed = current_version()
    if installed == SOURCE_VERSION:
        return Check("source", WARN,
                     "running from source; no installed version to compare")
    if installed == source_version:
        return Check("source", OK, f"installed {installed} matches {source}")
    return Check("source", FAIL,
                 f"installed {installed}, source {source_version} at {source}")


def run(agent: str, *, runner: Runner, binary: str = "hermes",
        probe_timeout: int = 60, source: Path | None = None) -> list[Check]:
    """Every check, in the order a failure matters most."""
    checks = [check_git(), check_reviewer(binary), check_sandbox(),
              check_agent(agent, runner, probe_timeout)]
    extra = check_source(source)
    if extra is not None:
        checks.append(extra)
    return checks
