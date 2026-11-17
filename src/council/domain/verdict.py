"""`judge(findings)` is the whole decision: no threshold, no score, no clock.
A number may sit beside a verdict as a trend; it cannot change it."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum

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


def exit_code(verdict: Verdict) -> int:
    """One mapping for every gate: 0 pass, 1 fail, 2 incomplete."""
    return {Verdict.PASS: 0, Verdict.FAIL: 1, Verdict.INCOMPLETE: 2}[verdict]


@dataclass(frozen=True, slots=True)
class Result:
    """A verdict and the evidence it was derived from."""

    verdict: Verdict
    reason: str
    findings: tuple[Finding, ...]

    @property
    def exit_code(self) -> int:
        """0 pass, 1 fail, 2 incomplete — a caller can gate on the number alone."""
        return exit_code(self.verdict)


def _cite(findings: list[Finding]) -> str:
    """Name the findings a human has to act on, without listing all of them."""
    shown = ", ".join(f.id for f in findings[:3])
    return shown if len(findings) <= 3 else f"{shown}, +{len(findings) - 3} more"


def judge(findings: Iterable[Finding], *, executed_only: bool = False) -> Result:
    """Derive the verdict from the findings' states.

    The rule, in full:
      1. any blocking finding that is PROVEN  -> FAIL
      2. else any blocking finding that is open -> INCOMPLETE
      3. else -> PASS

    Fail outranks incomplete: a run that has both a real defect and an unsettled
    claim is failing for a reason you can act on, and the unsettled claim is
    still visible in `findings`.

    A finding proven only by quotation is named in the reason whatever the rule
    does with it, and `executed_only` lets a caller refuse to block on one. The
    default stays lenient because a quoted line is often the whole defect —
    a hard-coded secret, a missing guard — and a caller who wants more says so.
    """
    items = tuple(findings)
    proven = [f for f in items if f.blocks and f.state is State.PROVEN]
    quoted = [f for f in proven if not f.executed]
    if executed_only:
        proven = [f for f in proven if f.executed]
    if proven:
        suffix = (f"; {len(quoted)} of them proven by quotation only"
                  if quoted and not executed_only else "")
        return Result(
            Verdict.FAIL,
            f"{len(proven)} proven blocking finding(s): {_cite(proven)}{suffix}",
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
    notes: list[str] = []
    if non_blocking:
        notes.append(f"{len(non_blocking)} proven non-blocking finding(s)")
    if quoted:
        notes.append(f"{len(quoted)} proven by quotation only: {_cite(quoted)}")
    suffix = f" ({'; '.join(notes)})" if notes else ""
    return Result(Verdict.PASS, f"no proven blocking findings{suffix}", items)
