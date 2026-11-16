"""Merging: by place, highest severity wins, every wording kept, order fixed."""

from __future__ import annotations

from typing import Any

from council.findings import blocks
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


def test_one_line_is_one_finding_whatever_the_dimension() -> None:
    """The place is the key: two labels for one defect are one defect."""
    merged = merge([sample(raw(dimension="security"), raw(dimension="readability"))])
    assert len(merged) == 1
    assert merged[0].dimension == "security"


def test_merging_never_weakens_a_finding() -> None:
    """If any sample's finding blocks, the merged one blocks.

    The old key was `(dimension, file, line)`, so this pair produced two rows and
    the merged label depended on which row a reader picked. Now the label is the
    most blocking dimension any sample used and the severity is the highest any
    sample claimed, so a merge can only preserve or raise blocking status.
    """
    merged = merge([sample(raw("medium", dimension="readability")),
                    sample(raw("low", dimension="correctness"))])
    assert len(merged) == 1
    assert merged[0].dimension == "correctness"
    assert merged[0].severity == "medium"
    assert blocks(merged[0].dimension, merged[0].severity)
    assert any(blocks(item.dimension, item.severity) for item in
               (raw("medium", dimension="readability"), raw("low", dimension="correctness")))


def test_two_non_blocking_dimensions_resolve_in_canonical_order() -> None:
    forward = merge([sample(raw(dimension="readability")),
                     sample(raw(dimension="performance"))])
    backward = merge([sample(raw(dimension="performance")),
                      sample(raw(dimension="readability"))])
    assert forward == backward
    assert forward[0].dimension == "readability"


def test_different_files_at_one_line_stay_separate() -> None:
    merged = merge([sample(raw(file="a.py", line=3), raw(file="b.py", line=3))])
    assert [(item.file, item.line) for item in merged] == [("a.py", 3), ("b.py", 3)]


def test_a_merged_finding_names_the_samples_it_came_from() -> None:
    """The trail: a finding points at the files whose answers asserted it."""
    merged = merge([sample(raw(claim="First.")), sample(raw(claim="Second."))],
                   labels=["sample-1.json", "sample-2.json"])
    assert merged[0].evidence == ("sample-1.json", "sample-2.json")


def test_a_failed_sample_leaves_a_hole_in_the_labels() -> None:
    merged = merge([sample(raw()), failed(), sample(raw(claim="Third."))],
                   labels=["sample-1.json", "sample-2.json", "sample-3.json"])
    assert merged[0].samples == (1, 3)
    assert merged[0].evidence == ("sample-1.json", "sample-3.json")


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
