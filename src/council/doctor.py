"""Can this machine run a review? Measure it before a review depends on it."""

from __future__ import annotations

import shutil
import time
from dataclasses import dataclass

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
        return f"{self.status:<4}  {self.name:<8}  {self.detail}"


def check_git() -> Check:
    path = shutil.which("git")
    return Check("git", OK, path) if path else Check("git", FAIL, "git is not on PATH")


def check_reviewer(binary: str) -> Check:
    path = shutil.which(binary)
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
        runner(PROBE)
    except Exception as exc:  # noqa: BLE001 - every failure is the finding here
        return Check("profile", FAIL, f"{profile}: {type(exc).__name__}: {exc}")
    seconds = time.monotonic() - started
    return Check("profile", OK,
                 f"{profile} answered in {seconds:.1f}s (probe limit {probe_timeout}s)")


def run(profile: str, *, runner: Runner, binary: str = "hermes",
        probe_timeout: int = 60) -> list[Check]:
    """Every check, in the order a failure matters most."""
    return [check_git(), check_reviewer(binary), check_sandbox(),
            check_profile(profile, runner, probe_timeout)]
