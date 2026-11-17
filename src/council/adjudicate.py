"""Run each finding's proof, then hand the outcomes to the pure adjudicator.

The decision — what a set of outcomes means — is in
`council.domain.adjudication`; this module is the shell that executes proofs.
"""

from __future__ import annotations

from collections.abc import Sequence

from .domain.adjudication import Adjudication, ProofOutcome, decide, verdict
from .domain.merge import MergedFinding
from .proofs import ProofContext, run_proof

__all__ = ["Adjudication", "ProofOutcome", "adjudicate", "verdict"]


def adjudicate(merged: Sequence[MergedFinding], ctx: ProofContext, *,
               failed_samples: Sequence[int] = ()) -> Adjudication:
    """Run each finding's proof and record what it settled."""
    outcomes = [
        [run_proof(kind, params, ctx) for kind, params in item.proofs]
        for item in merged
    ]
    return decide(merged, outcomes, failed_samples=failed_samples)
