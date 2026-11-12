"""Run each finding's proof, then hand the outcomes to the pure adjudicator.

The decision — what a set of outcomes means — is in
`council.domain.adjudication`; this module is the shell that executes proofs.
"""

from __future__ import annotations

from typing import Any, Callable, Sequence

from .domain.adjudication import Adjudication, ProofOutcome, decide, verdict
from .merge import MergedFinding
from .proofs import ProofContext, run_proof

Prover = Callable[[str, dict[str, Any], ProofContext], ProofOutcome]

__all__ = ["Adjudication", "ProofOutcome", "adjudicate", "verdict"]


def adjudicate(merged: Sequence[MergedFinding], ctx: ProofContext, *,
               failed_samples: Sequence[int] = (),
               prove: Prover = run_proof) -> Adjudication:
    """Run each finding's proof and record what it settled."""
    outcomes = [
        [prove(kind, params, ctx) for kind, params in item.proofs]
        for item in merged
    ]
    return decide(merged, outcomes, failed_samples=failed_samples)
