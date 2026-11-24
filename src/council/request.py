"""The caller's review request: selection, policy and output location.

This is a pure value object. It does not read the repository or the prompt; the
effect shell (`prepare`) does that. Keeping the request here stops `run.py` from
being the import point for every caller.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from .agents import DEFAULT_AGENT
from .domain.run_id import validate_run_id
from .domain.scope import Scope, ScopeError
from .domain.text import printable
from .pr import PullRequest

DEFAULT_PROFILE = "council-generalist"
PROMPT_LIMIT = 32 * 1024
#: The most windows one change may be split into. Past this the run is no longer
#: a review but a crawl, and refusing is cheaper than starting it.
WINDOW_LIMIT = 200


def _integer(label: str, value: object, *, minimum: int | None = None) -> int:
    """A request integer, rejecting bool (a subclass of int) and non-integers."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{label} must be an integer")  # noqa: TRY004 - request validation contract
    if minimum is not None and value < minimum:
        raise ValueError(f"{label} must be at least {minimum}")
    return value


@dataclass(frozen=True, slots=True)
class ReviewRequest:
    repo: Path
    base: str | None = None
    samples: int | None = None
    allow_single_sample: bool = False
    agent: str = DEFAULT_AGENT
    reviewer: str = ""
    profile: str = DEFAULT_PROFILE
    run_id: str | None = None
    prompt: Path | None = None
    context_urls: tuple[str, ...] = ()
    allow_large_prompt: bool = False
    max_prompt_bytes: int = PROMPT_LIMIT
    window_large_files: bool = False
    max_windows: int = WINDOW_LIMIT
    require_executed_proofs: bool = False
    context_depth: int = 3
    time_budget: int = 0
    reasoning: str | None = None
    stream: bool = False
    idle_timeout: int = 120
    sandbox: bool = False
    state_dir: Path | None = None
    pull_request: PullRequest | None = None
    baseline: Path | None = None
    baseline_from_base: bool = False
    baseline_strict: bool = False
    allow_baseline_change: bool = False
    allow_rules_change: bool = False
    include: tuple[str, ...] = ()
    exclude: tuple[str, ...] = ()
    staged: bool = False

    def validate(self) -> None:
        """Reject a malformed request before any repository or model work."""
        if not isinstance(self.allow_single_sample, bool):
            raise ValueError("allow_single_sample must be a boolean")
        if self.samples is not None:
            _integer("samples", self.samples, minimum=1)
            if self.samples == 1 and not self.allow_single_sample:
                raise ValueError("a one-sample review requires --allow-single-sample")
        _integer("the prompt limit", self.max_prompt_bytes, minimum=1)
        _integer("the window limit", self.max_windows, minimum=1)
        _integer("context depth", self.context_depth)
        _integer("the time budget", self.time_budget, minimum=0)
        _integer("the idle timeout", self.idle_timeout, minimum=1)
        if self.context_depth not in (0, 1, 2, 3):
            raise ValueError("context depth must be 0, 1, 2 or 3")
        if not isinstance(self.agent, str) or not self.agent.strip():
            raise ValueError("--agent must not be empty")
        if not printable(self.agent):
            raise ValueError("--agent must be printable text")
        if not isinstance(self.reviewer, str):
            raise ValueError("--reviewer must be text")
        if self.reviewer and not printable(self.reviewer):
            raise ValueError("--reviewer must be printable text")
        if not isinstance(self.profile, str) or not self.profile.strip():
            raise ValueError("--profile must not be empty")
        if not printable(self.profile):
            raise ValueError("--profile must be printable text")
        if self.base is not None and (not isinstance(self.base, str)
                                      or not self.base.strip()):
            raise ValueError("--base must not be empty")
        if self.run_id is not None and not isinstance(self.run_id, str):
            raise ValueError("run id must be text")
        validate_run_id(self.run_id if self.run_id is not None
                        else datetime.now(UTC).strftime("%Y%m%d-%H%M%S"))
        try:
            Scope.create(self.include, self.exclude)
        except ScopeError as exc:
            raise ValueError(str(exc)) from exc
