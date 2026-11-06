"""The verdict: one function, one type, three outcomes.

`judge(findings)` is the whole decision. It is a pure function over the states
the evidence reached — no threshold, no score, no calibration, no clock. A
number may be reported beside a verdict as a trend; it can never change it.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable

from .findings import OPEN_STATES, Finding, State


class Verdict(Enum):
    """What a run means for a merge.

    `PASS` — every blocking finding was refuted, or there were none.
    `FAIL` — at least one blocking finding was proven.
    `INCOMPLETE` — a blocking finding's claim was never settled, so the run knows
    it does not know. Distinct from `FAIL` on purpose: one is a defect to fix,
    the other is evidence to obtain.
    """

    PASS = "pass"
    FAIL = "fail"
    INCOMPLETE = "incomplete"


@dataclass(frozen=True, slots=True)
class Result:
    """A verdict and the evidence it was derived from."""

    verdict: Verdict
    reason: str
    findings: tuple[Finding, ...]

    @property
    def exit_code(self) -> int:
        """0 pass, 1 fail, 2 incomplete — a caller can gate on the number alone."""
        return {Verdict.PASS: 0, Verdict.FAIL: 1, Verdict.INCOMPLETE: 2}[self.verdict]


def _cite(findings: list[Finding]) -> str:
    """Name the findings a human has to act on, without listing all of them."""
    shown = ", ".join(f.id for f in findings[:3])
    return shown if len(findings) <= 3 else f"{shown}, +{len(findings) - 3} more"


def judge(findings: Iterable[Finding]) -> Result:
    """Derive the verdict from the findings' states.

    The rule, in full:
      1. any blocking finding that is PROVEN  -> FAIL
      2. else any blocking finding that is open -> INCOMPLETE
      3. else -> PASS

    Fail outranks incomplete: a run that has both a real defect and an unsettled
    claim is failing for a reason you can act on, and the unsettled claim is
    still visible in `findings`.
    """
    items = tuple(findings)
    proven = [f for f in items if f.blocks and f.state is State.PROVEN]
    if proven:
        return Result(
            Verdict.FAIL,
            f"{len(proven)} proven blocking finding(s): {_cite(proven)}",
            items,
        )

    open_blocking = [f for f in items if f.blocks and f.state in OPEN_STATES]
    if open_blocking:
        return Result(
            Verdict.INCOMPLETE,
            f"{len(open_blocking)} blocking finding(s) could not be settled: {_cite(open_blocking)}",
            items,
        )

    non_blocking = [f for f in items if not f.blocks and f.state is State.PROVEN]
    suffix = f" ({len(non_blocking)} proven non-blocking finding(s))" if non_blocking else ""
    return Result(Verdict.PASS, f"no proven blocking findings{suffix}", items)