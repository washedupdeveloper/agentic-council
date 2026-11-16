"""Merge by place: one line is one finding, and the most blocking dimension wins.

The key used to be `(dimension, file, line)`, which let a label decide the gate:
two samples that agreed a line was defective but disagreed about its category
produced two findings, and the run failed only if one of them happened to be
filed under a blocking dimension. A model that calls a defect `readability` could
therefore launder it past the gate.

The key is the place. The dimension is adjudicated from what the samples said —
the most blocking one wins — and severity is the highest any of them claimed, so
disagreement can raise a finding but never lower it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from .findings import ALWAYS_BLOCKING, SEVERITIES
from .schema import DIMENSIONS, RawFinding

_RANK: dict[str, int] = {severity: index for index, severity in enumerate(SEVERITIES)}
_ORDER: dict[str, int] = {dimension: index for index, dimension in enumerate(DIMENSIONS)}


def _dimension_rank(dimension: str) -> tuple[int, int]:
    """Blocking dimensions first, then the canonical order — never the model's order.

    `security` and `correctness` block at any severity, so a disagreement that
    mentions either resolves to it. Nothing about this ranking is the model's to
    choose: it is the same rule `findings.blocks` already applies.
    """
    return (0 if dimension in ALWAYS_BLOCKING else 1,
            _ORDER.get(dimension, len(DIMENSIONS)))


@dataclass(frozen=True, slots=True)
class MergedFinding:
    """One place in the change, as reported by one or more samples."""

    dimension: str
    file: str
    line: int
    severity: str
    claims: tuple[str, ...]
    samples: tuple[int, ...]
    proofs: tuple[tuple[str, dict[str, Any]], ...]


def merge(samples: Sequence[Sequence[RawFinding]]) -> tuple[MergedFinding, ...]:
    """Merge findings per sample, deterministically.

    A failed sample is an empty list, and the sample number is its position, so
    a failure stays a hole instead of renumbering the samples after it.
    """
    buckets: dict[tuple[str, int], list[tuple[int, RawFinding]]] = {}
    for number, findings in enumerate(samples, start=1):
        for finding in findings:
            key = (finding.file, finding.line)
            buckets.setdefault(key, []).append((number, finding))

    merged: list[MergedFinding] = []
    for key in sorted(buckets):
        entries = sorted(buckets[key], key=lambda entry: entry[0])
        highest = max(entries, key=lambda entry: _RANK[entry[1].severity])
        dimension = min((finding.dimension for _, finding in entries),
                        key=_dimension_rank)
        claims = tuple(dict.fromkeys(finding.claim for _, finding in entries))
        proofs: list[tuple[str, dict[str, Any]]] = []
        for _, finding in entries:
            proof = (finding.proof_kind, finding.proof_params)
            if proof not in proofs:
                proofs.append(proof)
        merged.append(MergedFinding(
            dimension=dimension,
            file=key[0],
            line=key[1],
            severity=highest[1].severity,
            claims=claims,
            samples=tuple(sorted(index for index, _ in entries)),
            proofs=tuple(proofs),
        ))
    return tuple(merged)
