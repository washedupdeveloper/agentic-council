"""Pure adjudication: proof outcomes in, findings and verdict out.

The execution of proofs is the effect shell (`council.adjudicate` /
`council.proofs`); deciding what a set of outcomes means is here.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, cast

from .findings import EXECUTED_PROOF_KINDS, Finding, Severity, State
from .merge import MergedFinding
from .verdict import Result, Verdict, judge


def canonical_proof(proofs: Sequence[tuple[str, Mapping[str, Any]]]) -> str:
    """A stable text identity for the proof list, independent of dict order."""
    items = [[kind, dict(params)] for kind, params in proofs]
    return json.dumps(items, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, default=str)


@dataclass(frozen=True, slots=True)
class ProofOutcome:
    """What one proof settled, independent of how it was run."""

    state: State
    detail: str
    #: Which proof kind settled it. Empty when a caller built the outcome by
    #: hand, which counts as not demonstrated by execution.
    kind: str = ""


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
            file=item.file,
            line=item.line,
            claim=item.claims[0] if item.claims else "",
            detail=detail,
            proof=canonical_proof(item.proofs),
            executed=any(o.kind in EXECUTED_PROOF_KINDS for o in proven),
            evidence=item.evidence,
        ))
    return Adjudication(tuple(findings), tuple(sorted(failed_samples)))


def _masked(result: Result, note: str) -> Result:
    """Record missing evidence without ever softening it.

    `PASS` cannot survive a unit or a sample that was never reviewed, so it
    becomes `INCOMPLETE`; `FAIL` and `INCOMPLETE` keep their verdict and gain
    the note, because the reason must still say what was not looked at.
    """
    if result.verdict is Verdict.PASS:
        return Result(Verdict.INCOMPLETE,
                      f"{note}: the review is missing evidence", result.findings)
    return Result(result.verdict, f"{result.reason}; {note}", result.findings)


def missing_evidence(result: Result, *, silent: Sequence[str] = (),
                     late: Sequence[str] = (), budget: int = 0) -> Result:
    """Units that returned nothing usable, or were never asked inside the budget."""
    notes: list[str] = []
    if silent:
        notes.append(f"unit(s) {', '.join(silent)} returned nothing usable")
    if late:
        notes.append(f"unit(s) {', '.join(late)} were not reviewed within "
                     f"the {budget}s time budget")
    return _masked(result, "; ".join(notes)) if notes else result


def verdict(adjudication: Adjudication, *,
            executed_only: bool = False) -> Result:
    """The verdict, with one addition the findings cannot express.

    A sample that returned nothing usable means the review is missing evidence.
    If the evidence that did arrive already fails the run, fail; otherwise the
    honest answer is `INCOMPLETE`, never `PASS`.

    `executed_only` is the caller's answer to a quarrel about proof strength: a
    quotation can show that a line exists, not that the code misbehaves, so a
    caller may require a proof that ran something before it lets it block.
    """
    result = judge(adjudication.findings, executed_only=executed_only)
    if adjudication.failed_samples:
        listed = ", ".join(str(index) for index in adjudication.failed_samples)
        return _masked(result, f"sample(s) {listed} returned nothing usable")
    return result
