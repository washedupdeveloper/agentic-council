"""Merging: by place, highest severity wins, every wording kept, order fixed."""

from __future__ import annotations

from typing import Any

from council.merge import merge
from council.sample import SampleResult
from council.schema import RawFinding, ReviewerOutput


def raw(severity: str = "high", file: str = "a.py", line: int = 3,
        claim: str = "It is wrong.", dimension: str = "correctness",
        kind: str = "present") -> RawFinding:
    params: dict[str, Any] = {"path": file, "line": line, "text": "x"}
    return RawFinding(dimension=dimension, severity=severity, file=file, line=line,
                      claim=claim, proof_kind=kind, proof_params=params)


def sample(index: int, *findings: RawFinding) -> SampleResult:
    return SampleResult(index=index, output=ReviewerOutput(tuple(findings)), attempts=1, error=None)


def failed(index: int) -> SampleResult:
    return SampleResult(index=index, output=None, attempts=2, error="not json")


def test_the_same_place_in_two_samples_is_one_finding() -> None:
    merged = merge([sample(1, raw()), sample(2, raw(claim="It is wrong, again."))])
    assert len(merged) == 1
    assert merged[0].samples == (1, 2)
    assert merged[0].claims == ("It is wrong.", "It is wrong, again.")


def test_the_highest_severity_wins() -> None:
    merged = merge([sample(1, raw("medium")), sample(2, raw("critical"))])
    assert merged[0].severity == "critical"


def test_the_highest_severity_wins_whatever_the_order() -> None:
    forward = merge([sample(1, raw("low")), sample(2, raw("high"))])
    backward = merge([sample(2, raw("high")), sample(1, raw("low"))])
    assert forward == backward


def test_different_lines_stay_separate() -> None:
    merged = merge([sample(1, raw(line=3), raw(line=9))])
    assert [item.line for item in merged] == [3, 9]


def test_different_dimensions_at_one_line_stay_separate() -> None:
    merged = merge([sample(1, raw(dimension="security"), raw(dimension="readability"))])
    assert len(merged) == 2
    assert merged[0].dimension == "security"


def test_a_failed_sample_contributes_nothing() -> None:
    merged = merge([sample(1, raw()), failed(2)])
    assert len(merged) == 1
    assert merged[0].samples == (1,)


def test_the_output_order_is_fixed() -> None:
    merged = merge([sample(1, raw(line=9)), sample(2, raw(line=3))])
    assert [item.line for item in merged] == [3, 9]


def test_every_samples_proof_is_kept() -> None:
    low = raw("low", kind="absent")
    high = raw("high", kind="command")
    merged = merge([sample(1, low), sample(2, high)])
    assert [kind for kind, _ in merged[0].proofs] == ["absent", "command"]


def test_no_samples_merge_to_nothing() -> None:
    assert merge([]) == ()