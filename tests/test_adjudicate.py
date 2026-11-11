"""Adjudication: proofs become states, and a missing sample cannot become a pass."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from council.adjudicate import adjudicate, verdict
from council.findings import State
from council.merge import MergedFinding
from council.proofs import ProofContext
from council.verdict import Verdict

ALLOW = frozenset({"true"})


def ctx(repo: Path) -> ProofContext:
    return ProofContext(repo=repo, allow=ALLOW, diff=None, timeout=5, sandbox=False)


def merged(severity: str = "high", kind: str = "present",
           params: dict[str, Any] | None = None,
           dimension: str = "correctness") -> MergedFinding:
    return MergedFinding(
        dimension=dimension, file="a.py", line=2, severity=severity,
        claims=("It is wrong.",), samples=(1,),
        proofs=((kind, params or {"path": "a.py", "line": 2, "text": "two"}),),
    )


def repo_with(tmp_path: Path) -> Path:
    (tmp_path / "a.py").write_text("one\ntwo\n", encoding="utf-8")
    return tmp_path


def test_a_proof_that_holds_makes_the_finding_proven(tmp_path: Path) -> None:
    adj = adjudicate([merged()], ctx(repo_with(tmp_path)))
    finding = adj.findings[0]
    assert finding.state is State.PROVEN
    assert finding.id == "F-01"
    assert finding.location == "a.py:2"
    assert finding.detail


def test_a_proof_that_fails_makes_the_finding_refuted(tmp_path: Path) -> None:
    adj = adjudicate([merged(params={"path": "a.py", "line": 2, "text": "three"})],
                     ctx(repo_with(tmp_path)))
    assert adj.findings[0].state is State.REFUTED


def test_a_proof_that_cannot_run_is_unrunnable(tmp_path: Path) -> None:
    adj = adjudicate([merged(kind="command", params={"argv": ["curl", "http://example.invalid"]})],
                     ctx(repo_with(tmp_path)))
    assert adj.findings[0].state is State.UNRUNNABLE


def test_any_proof_that_holds_settles_the_finding(tmp_path: Path) -> None:
    """Two samples, two proofs: one refuted and one proven is still a proven finding."""
    item = MergedFinding(
        dimension="correctness", file="a.py", line=2, severity="high",
        claims=("It is wrong.",), samples=(1, 2),
        proofs=(("present", {"path": "a.py", "line": 2, "text": "three"}),
                ("present", {"path": "a.py", "line": 1, "text": "one"})),
    )
    adj = adjudicate([item], ctx(repo_with(tmp_path)))
    assert adj.findings[0].state is State.PROVEN


def test_ids_are_sequential_and_zero_padded(tmp_path: Path) -> None:
    first = merged()
    second = merged(severity="low")
    adj = adjudicate([first, second], ctx(repo_with(tmp_path)))
    assert [f.id for f in adj.findings] == ["F-01", "F-02"]


def test_a_proven_blocking_finding_fails_the_run(tmp_path: Path) -> None:
    result = verdict(adjudicate([merged()], ctx(repo_with(tmp_path))))
    assert result.verdict is Verdict.FAIL
    assert result.exit_code == 1


def test_a_proven_low_finding_passes_the_run(tmp_path: Path) -> None:
    """Severity still matters outside security and correctness."""
    result = verdict(adjudicate([merged(severity="low", dimension="readability")],
                                ctx(repo_with(tmp_path))))
    assert result.verdict is Verdict.PASS


def test_a_missing_sample_makes_an_otherwise_clean_run_incomplete(tmp_path: Path) -> None:
    adj = adjudicate([], ctx(repo_with(tmp_path)), failed_samples=[2])
    result = verdict(adj)
    assert result.verdict is Verdict.INCOMPLETE
    assert result.exit_code == 2
    assert "2" in result.reason


def test_a_missing_sample_does_not_soften_a_real_failure(tmp_path: Path) -> None:
    adj = adjudicate([merged()], ctx(repo_with(tmp_path)), failed_samples=[2])
    result = verdict(adj)
    assert result.verdict is Verdict.FAIL
    assert "sample(s) 2" in result.reason


def test_a_clean_run_with_no_findings_passes(tmp_path: Path) -> None:
    adj = adjudicate([], ctx(repo_with(tmp_path)))
    assert verdict(adj).verdict is Verdict.PASS
