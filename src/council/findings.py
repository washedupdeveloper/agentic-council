"""A finding is a claim; its state says what the evidence settled.

The vocabulary is closed on purpose: four states, four severities, and one
predicate (`blocks`) that decides whether the state matters to the verdict.
There is no `confirmed`, no `certified`, no `admission` — a reader who has seen
`State` knows everything the verdict can depend on.
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

    @property
    def blocks(self) -> bool:
        """Whether this finding's severity can fail a run at all."""
        return self.severity in BLOCKING

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("a finding needs an id: the verdict cites it")
        if self.severity not in SEVERITIES:
            raise ValueError(f"unknown severity {self.severity!r}; expected one of {SEVERITIES}")