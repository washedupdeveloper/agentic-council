"""Can this machine run a review? Measure it before a review depends on it."""

from __future__ import annotations

import os
import shutil
import time
from dataclasses import dataclass
from pathlib import Path

from .domain.text import sanitize
from .sample import Runner

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
        return f"{self.status:<4}  {self.name:<8}  {_safe(self.detail)}"


def _safe(text: object) -> str:
    """One printable line: a profile name or an error must not drive the terminal."""
    return sanitize(text)


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


def check_profile(profile: str, runner: Runner, probe_timeout: int) -> Check:
    """Ask the profile a question it must answer quickly."""
    started = time.monotonic()
    try:
        answer = runner(PROBE)
    except Exception as exc:  # noqa: BLE001 - every failure is the finding here
        return Check("profile", FAIL, f"{profile}: {type(exc).__name__}: {exc}")
    seconds = time.monotonic() - started
    if not isinstance(answer, str) or not answer.strip():
        return Check("profile", FAIL, f"{profile}: the probe returned nothing")
    return Check("profile", OK,
                 f"{profile} answered in {seconds:.1f}s (probe limit {probe_timeout}s)")


def run(profile: str, *, runner: Runner, binary: str = "hermes",
        probe_timeout: int = 60) -> list[Check]:
    """Every check, in the order a failure matters most."""
    return [check_git(), check_reviewer(binary), check_sandbox(),
            check_profile(profile, runner, probe_timeout)]
