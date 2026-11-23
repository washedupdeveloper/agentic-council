"""What a proof was worth: quotation versus execution, and a verdict written whole.

A `present` proof shows a line exists; only `command` and `repro` demonstrate
behaviour. The distinction became unavoidable when reviewing deepseek-harness,
where a reviewer proved claims about control flow by quoting the line that
contained the defect. The default still blocks on a quotation and says so in the
reason; `--require-executed-proofs` is the caller's choice to refuse.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from council.repo import ReviewError
from council.run import ReviewRequest, review
from council.runstore import SCOPE_REPORT_LIMIT, VERDICT_FORMAT, bounded
from council.domain.schema import DIMENSIONS
from council.domain.verdict import Verdict


def git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=repo, check=True,
                          capture_output=True, text=True).stdout.strip()


def make_repo(tmp_path: Path) -> Path:
    git(tmp_path, "init", "-q")
    git(tmp_path, "config", "user.email", "test@example.invalid")
    git(tmp_path, "config", "user.name", "test")
    (tmp_path / "f0.py").write_text("# base\n", encoding="utf-8")
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-qm", "base")
    (tmp_path / "f1.py").write_text("# second\n", encoding="utf-8")
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-qm", "second")
    (tmp_path / "a.py").write_text("one\ntwo\n", encoding="utf-8")
    return tmp_path


def body(findings: dict[str, list[dict[str, Any]]] | None = None) -> str:
    sections: dict[str, list[dict[str, Any]]] = {name: [] for name in DIMENSIONS}
    sections.update(findings or {})
    return json.dumps({"sections": sections})


def quoted() -> dict[str, Any]:
    """A security finding proven by quoting a line: not a demonstration."""
    return {"severity": "high", "file": "a.py", "line": 2, "claim": "It is wrong.",
            "proof": {"kind": "present",
                      "params": {"path": "a.py", "line": 2, "text": "two"}}}


def executed() -> dict[str, Any]:
    """A finding whose proof ran a command, which is evidence of behaviour."""
    return {"severity": "high", "file": "a.py", "line": 1, "claim": "It is wrong.",
            "proof": {"kind": "command",
                      "params": {"argv": ["test", "-f", "a.py"],
                                 "expect": {"exit": "zero"}}}}


def payload_of(report: Any) -> dict[str, Any]:
    return json.loads((report.run_dir / "verdict.json").read_text(encoding="utf-8"))


def test_a_quotation_only_finding_is_named_in_the_reason(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    report = review(ReviewRequest(repo=repo, samples=1, allow_single_sample=True, run_id="lenient"),
                    lambda _: body({"security": [quoted()]}))
    assert report.verdict is Verdict.FAIL
    assert "proven by quotation only" in report.reason


def test_a_quotation_only_finding_is_incomplete_under_strict_mode(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    report = review(ReviewRequest(repo=repo, samples=1, allow_single_sample=True, run_id="strict",
                                  require_executed_proofs=True),
                    lambda _: body({"security": [quoted()]}))
    assert report.verdict is Verdict.INCOMPLETE
    assert "proven by quotation only" in report.reason
    assert "F-01" in report.reason
    payload = payload_of(report)
    assert payload["findings"][0]["proof_strength"] == "static"
    assert payload["findings"][0]["state"] == "proven"
    assert payload["require_executed_proofs"] is True


def test_a_quotation_only_non_blocking_finding_passes_strict_mode(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    finding = quoted()
    finding.update({"severity": "low", "claim": "Style nit."})
    report = review(ReviewRequest(repo=repo, samples=1, allow_single_sample=True, run_id="strict-note",
                                  require_executed_proofs=True),
                    lambda _: body({"readability": [finding]}))
    assert report.verdict is Verdict.PASS
    assert "F-01" in report.reason
    assert "quotation only" in report.reason
    assert payload_of(report)["findings"][0]["proof_strength"] == "static"


def test_an_executed_proof_still_blocks_a_strict_run(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    report = review(ReviewRequest(repo=repo, samples=1, allow_single_sample=True, run_id="executed",
                                  require_executed_proofs=True),
                    lambda _: body({"security": [executed()]}))
    assert report.verdict is Verdict.FAIL
    assert payload_of(report)["findings"][0]["proof_strength"] == "executed"


def test_the_verdict_names_its_format(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    report = review(ReviewRequest(repo=repo, samples=1, allow_single_sample=True, run_id="format"),
                    lambda _: body())
    assert payload_of(report)["format"] == VERDICT_FORMAT


def test_a_verdict_that_cannot_be_published_leaves_no_partial_file(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The staging file is removed and the target is never written in place."""
    repo = make_repo(tmp_path)

    def refuse(source: object, target: object) -> None:
        raise OSError("no space left on device")

    monkeypatch.setattr("council.runstore.os.replace", refuse)
    with pytest.raises(ReviewError, match="cannot write"):
        review(ReviewRequest(repo=repo, samples=1, allow_single_sample=True, run_id="atomic"), lambda _: body())
    run_dir = repo / ".council" / "runs" / "atomic"
    assert not (run_dir / "verdict.json").exists()
    assert not list(run_dir.glob("*.tmp"))
    assert not list(run_dir.glob(".*.tmp"))


def test_the_scope_report_is_bounded_and_counts_the_rest(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    for index in range(205):
        (repo / f"extra{index}.py").write_text("# x\n", encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "extras")

    report = review(ReviewRequest(repo=repo, samples=1, allow_single_sample=True, run_id="bounded",
                                  include=("a.py",)), lambda _: body())
    payload = payload_of(report)
    listed = len(payload["scope_ignored"])
    omitted = payload["scope_ignored_omitted"]
    assert listed == SCOPE_REPORT_LIMIT
    assert omitted > 0
    # The diff against HEAD~1 carries a.py and 205 extra files; f0/f1 are
    # unchanged, so they were never in scope to be dropped.
    assert listed + omitted == 205


def test_bounded_names_the_limit_and_counts_the_rest() -> None:
    listed, omitted = bounded([str(index) for index in range(300)], limit=200)
    assert len(listed) == 200
    assert listed[0] == "0" and listed[-1] == "199"
    assert omitted == 100
    assert bounded(["one"], limit=200) == (["one"], 0)


def test_a_strict_run_names_a_quotation_only_finding_beside_an_executed_one(
        tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    report = review(ReviewRequest(repo=repo, samples=1, allow_single_sample=True, run_id="strict-both",
                                  require_executed_proofs=True),
                    lambda _: body({"security": [executed(), quoted()]}))
    assert report.verdict is Verdict.FAIL
    assert "F-01" in report.reason
    assert "F-02" in report.reason
    assert "proven by quotation only" in report.reason
