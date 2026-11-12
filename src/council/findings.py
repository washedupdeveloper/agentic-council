"""A finding is a claim; its state says what the evidence settled.

Four states, four severities, one `blocks` predicate. No `confirmed`,
`certified` or `admission`: a reader who knows `State` knows the verdict.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Literal

#: The only severities a finding may carry. Ordered, and `BLOCKING` is derived
#: from this tuple rather than restated, so a new severity cannot be blocking in
#: one place and not in another.
Severity = Literal["low", "medium", "high", "critical"]
SEVERITIES: tuple[Severity, ...] = ("low", "medium", "high", "critical")
BLOCKING: frozenset[Severity] = frozenset({"high", "critical"})

#: Dimensions whose proven finding blocks at any severity. The model may rank a
#: defect; it may not decide that a proven security or correctness defect is
#: mergeable. This is the tool's rule, not the model's.
ALWAYS_BLOCKING: frozenset[str] = frozenset({"security", "correctness"})


def blocks(dimension: str, severity: str) -> bool:
    """Whether a proven finding of this dimension and severity fails a run."""
    return severity in BLOCKING or dimension in ALWAYS_BLOCKING


class State(Enum):
    """What the run's own check settled about a finding's claim.

    `PROVEN` is the only state that can fail a run: the check ran and supported
    the claim. `REFUTED` clears it. `UNSETTLED` and `UNRUNNABLE` are both "no
    answer" — one because nothing was tried, one because the thing could not run
    here — and either makes the run `INCOMPLETE`, never `PASS`.
    """

    PROVEN = "proven"
    REFUTED = "refuted"
    UNSETTLED = "unsettled"
    UNRUNNABLE = "unrunnable"


#: The states that mean "no answer yet". A blocking finding in one of these
#: stops the run from passing; it does not fail it.
OPEN_STATES: frozenset[State] = frozenset({State.UNSETTLED, State.UNRUNNABLE})


@dataclass(frozen=True, slots=True)
class Finding:
    """One claim about the change, and the state its evidence reached."""

    id: str
    dimension: str
    severity: Severity
    state: State
    location: str = ""
    claim: str = ""
    detail: str = ""
    #: Canonical proof identity, used only by the baseline policy. It is not a
    #: state and cannot change `blocks` or the verdict.
    proof: str = ""

    @property
    def blocks(self) -> bool:
        """Whether this finding's dimension and severity can fail a run at all."""
        return blocks(self.dimension, self.severity)

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("a finding needs an id: the verdict cites it")
        if self.severity not in SEVERITIES:
            raise ValueError(f"unknown severity {self.severity!r}; expected one of {SEVERITIES}")
