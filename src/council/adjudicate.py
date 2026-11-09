"""Proofs become states. A missing sample makes a run INCOMPLETE unless the
evidence already fails it."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence, cast

from .findings import Finding, Severity, State
from .merge import MergedFinding
from .proofs import ProofContext, run_proof
from .verdict import Result, Verdict, judge


@dataclass(frozen=True, slots=True)
class Adjudication:
    findings: tuple[Finding, ...]
    failed_samples: tuple[int, ...] = ()


def adjudicate(merged: Sequence[MergedFinding], ctx: ProofContext, *,
               failed_samples: Sequence[int] = ()) -> Adjudication:
    """Run each finding's proof and record what it settled."""
    findings: list[Finding] = []
    for number, item in enumerate(merged, start=1):
        outcomes = [run_proof(kind, params, ctx) for kind, params in item.proofs]
        proven = [o for o in outcomes if o.state is State.PROVEN]
        unrunnable = [o for o in outcomes if o.state is State.UNRUNNABLE]
        if proven:
            state, detail = State.PROVEN, proven[0].detail
        elif unrunnable:
            state, detail = State.UNRUNNABLE, unrunnable[0].detail
        else:
            state, detail = State.REFUTED, (outcomes[0].detail if outcomes else "no proof")
        findings.append(Finding(
            id=f"F-{number:02d}",
            dimension=item.dimension,
            severity=cast(Severity, item.severity),
            state=state,
            location=f"{item.file}:{item.line}",
            claim=item.claims[0] if item.claims else "",
            detail=detail,
        ))
    return Adjudication(tuple(findings), tuple(sorted(failed_samples)))


def verdict(adjudication: Adjudication) -> Result:
    """The verdict, with one addition the findings cannot express.

    A sample that returned nothing usable means the review is missing evidence.
    If the evidence that did arrive already fails the run, fail; otherwise the
    honest answer is `INCOMPLETE`, never `PASS`.
    """
    result = judge(adjudication.findings)
    if adjudication.failed_samples and result.verdict is Verdict.PASS:
        listed = ", ".join(str(index) for index in adjudication.failed_samples)
        return Result(
            Verdict.INCOMPLETE,
            f"sample(s) {listed} returned nothing usable: the review is missing evidence",
            adjudication.findings,
        )
    return result
