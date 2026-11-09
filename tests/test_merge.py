"""Merging: by place, highest severity wins, every wording kept, order fixed."""

from __future__ import annotations

from typing import Any

from council.merge import merge
from council.schema import RawFinding


def raw(severity: str = "high", file: str = "a.py", line: int = 3,
        claim: str = "It is wrong.", dimension: str = "correctness",
        kind: str = "present") -> RawFinding:
    params: dict[str, Any] = {"path": file, "line": line, "text": "x"}
    return RawFinding(dimension=dimension, severity=severity, file=file, line=line,
                      claim=claim, proof_kind=kind, proof_params=params)


def sample(*findings: RawFinding) -> list[RawFinding]:
    """One sample's findings. The sample's number is its position in the list."""
    return list(findings)


def failed() -> list[RawFinding]:
    return []


def test_the_same_place_in_two_samples_is_one_finding() -> None:
    merged = merge([sample(raw()), sample(raw(claim="It is wrong, again."))])
    assert len(merged) == 1
    assert merged[0].samples == (1, 2)
    assert merged[0].claims == ("It is wrong.", "It is wrong, again.")


def test_the_highest_severity_wins() -> None:
    merged = merge([sample(raw("medium")), sample(raw("critical"))])
    assert merged[0].severity == "critical"


def test_the_highest_severity_wins_whatever_the_order() -> None:
    forward = merge([sample(raw("low")), sample(raw("high"))])
    backward = merge([sample(raw("high")), sample(raw("low"))])
    assert forward == backward


def test_different_lines_stay_separate() -> None:
    merged = merge([sample(raw(line=3), raw(line=9))])
    assert [item.line for item in merged] == [3, 9]


def test_different_dimensions_at_one_line_stay_separate() -> None:
    merged = merge([sample(raw(dimension="security"), raw(dimension="readability"))])
    assert len(merged) == 2
    assert merged[0].dimension == "security"


def test_a_failed_sample_contributes_nothing() -> None:
    merged = merge([sample(raw()), failed()])
    assert len(merged) == 1
    assert merged[0].samples == (1,)


def test_a_failure_does_not_renumber_the_samples_after_it() -> None:
    """Sample 2 failed; the finding from the third sample is still sample 3."""
    merged = merge([sample(raw()), failed(), sample(raw(claim="Third."))])
    assert merged[0].samples == (1, 3)


def test_the_output_order_is_fixed() -> None:
    merged = merge([sample(raw(line=9)), sample(raw(line=3))])
    assert [item.line for item in merged] == [3, 9]


def test_every_samples_proof_is_kept() -> None:
    low = raw("low", kind="absent")
    high = raw("high", kind="command")
    merged = merge([sample(low), sample(high)])
    assert [kind for kind, _ in merged[0].proofs] == ["absent", "command"]


def test_no_samples_merge_to_nothing() -> None:
    assert merge([]) == ()
