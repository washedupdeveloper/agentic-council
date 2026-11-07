"""Merge by (dimension, file, line); highest severity wins; order fixed."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from .findings import SEVERITIES
from .schema import DIMENSIONS, RawFinding

_RANK: dict[str, int] = {severity: index for index, severity in enumerate(SEVERITIES)}
_ORDER: dict[str, int] = {dimension: index for index, dimension in enumerate(DIMENSIONS)}


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
    buckets: dict[tuple[str, str, int], list[tuple[int, RawFinding]]] = {}
    for number, findings in enumerate(samples, start=1):
        for finding in findings:
            key = (finding.dimension, finding.file, finding.line)
            buckets.setdefault(key, []).append((number, finding))

    merged: list[MergedFinding] = []
    for key in sorted(buckets, key=lambda k: (_ORDER[k[0]], k[1], k[2])):
        entries = sorted(buckets[key], key=lambda entry: entry[0])
        highest = max(entries, key=lambda entry: _RANK[entry[1].severity])
        claims = tuple(dict.fromkeys(finding.claim for _, finding in entries))
        proofs: list[tuple[str, dict[str, Any]]] = []
        for _, finding in entries:
            proof = (finding.proof_kind, finding.proof_params)
            if proof not in proofs:
                proofs.append(proof)
        merged.append(MergedFinding(
            dimension=key[0],
            file=key[1],
            line=key[2],
            severity=highest[1].severity,
            claims=claims,
            samples=tuple(sorted(index for index, _ in entries)),
            proofs=tuple(proofs),
        ))
    return tuple(merged)