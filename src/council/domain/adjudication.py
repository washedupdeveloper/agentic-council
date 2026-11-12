"""Pure adjudication: proof outcomes in, findings and verdict out.

The execution of proofs is the effect shell (`council.adjudicate` /
`council.proofs`); deciding what a set of outcomes means is here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence, cast

from ..findings import Finding, Severity, State
from ..merge import MergedFinding
from ..verdict import Result, Verdict, judge
from .proof import canonical_proof


@dataclass(frozen=True, slots=True)
class ProofOutcome:
    """What one proof settled, independent of how it was run."""

    state: State
    detail: str


@dataclass(frozen=True, slots=True)
class Adjudication:
    findings: tuple[Finding, ...]
    failed_samples: tuple[int, ...] = ()


def decide(merged: Sequence[MergedFinding],
           outcomes: Sequence[Sequence[ProofOutcome]], *,
           failed_samples: Sequence[int] = ()) -> Adjudication:
    """Decide each finding from its already-computed proof outcomes.

    `outcomes[i]` belongs to `merged[i]`; a count mismatch is a caller bug and
    is refused rather than silently zipped.
    """
    if len(merged) != len(outcomes):
        raise ValueError(
            f"adjudication needs one outcome group per finding: "
            f"{len(merged)} findings, {len(outcomes)} groups")
    findings: list[Finding] = []
    for number, (item, item_outcomes) in enumerate(zip(merged, outcomes), start=1):
        proven = [o for o in item_outcomes if o.state is State.PROVEN]
        unrunnable = [o for o in item_outcomes if o.state is State.UNRUNNABLE]
        if proven:
            state, detail = State.PROVEN, proven[0].detail
        elif unrunnable:
            state, detail = State.UNRUNNABLE, unrunnable[0].detail
        else:
            state, detail = State.REFUTED, (
                item_outcomes[0].detail if item_outcomes else "no proof")
        findings.append(Finding(
            id=f"F-{number:02d}",
            dimension=item.dimension,
            severity=cast(Severity, item.severity),
            state=state,
            location=f"{item.file}:{item.line}",
            claim=item.claims[0] if item.claims else "",
            detail=detail,
            proof=canonical_proof(item.proofs),
        ))
    return Adjudication(tuple(findings), tuple(sorted(failed_samples)))


def verdict(adjudication: Adjudication) -> Result:
    """The verdict, with one addition the findings cannot express.

    A sample that returned nothing usable means the review is missing evidence.
    If the evidence that did arrive already fails the run, fail; otherwise the
    honest answer is `INCOMPLETE`, never `PASS`.
    """
    result = judge(adjudication.findings)
    if adjudication.failed_samples:
        listed = ", ".join(str(index) for index in adjudication.failed_samples)
        if result.verdict is Verdict.PASS:
            return Result(
                Verdict.INCOMPLETE,
                f"sample(s) {listed} returned nothing usable: the review is missing evidence",
                adjudication.findings,
            )
        return Result(
            result.verdict,
            f"{result.reason}; sample(s) {listed} returned nothing usable",
            adjudication.findings,
        )
    return result
