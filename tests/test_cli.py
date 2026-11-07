"""The CLI is a thin adapter: parse, call, map the verdict to an exit code."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

import council.cli as cli
from council.findings import Finding, State
from council.run import Report, ReviewError
from council.verdict import Result, Verdict


def report(verdict: Verdict, *, run_dir: Path | None = None,
           findings: tuple[Finding, ...] = ()) -> Report:
    return Report(
        run_dir=run_dir or Path("/nonexistent"),
        base="a" * 40,
        head="b" * 40,
        digest="d" * 16,
        result=Result(verdict, "a reason", findings),
        samples=(),
    )


def stub(monkeypatch: pytest.MonkeyPatch, result: Report) -> None:
    monkeypatch.setattr(cli, "review", lambda request, runner: result)


def test_pass_exits_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    stub(monkeypatch, report(Verdict.PASS))
    assert cli.main(["review"]) == 0


def test_fail_exits_one(monkeypatch: pytest.MonkeyPatch) -> None:
    stub(monkeypatch, report(Verdict.FAIL))
    assert cli.main(["review"]) == 1


def test_incomplete_exits_two(monkeypatch: pytest.MonkeyPatch) -> None:
    stub(monkeypatch, report(Verdict.INCOMPLETE))
    assert cli.main(["review"]) == 2


def test_report_mode_exits_zero_even_on_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    stub(monkeypatch, report(Verdict.FAIL))
    assert cli.main(["review", "--report"]) == 0


def test_a_review_that_cannot_start_exits_three(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(request: Any, runner: Any) -> Report:
        raise ReviewError("no reviewer prompt")

    monkeypatch.setattr(cli, "review", boom)
    assert cli.main(["review"]) == 3


def test_a_usage_error_exits_three() -> None:
    with pytest.raises(SystemExit) as raised:
        cli.main(["review", "--samples", "not-a-number"])
    assert raised.value.code == 3


def test_the_defaults_are_passed_through(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, Any] = {}

    def capture(request: Any, runner: Any) -> Report:
        seen["request"] = request
        return report(Verdict.PASS)

    monkeypatch.setattr(cli, "review", capture)
    assert cli.main(["review", "-C", "/tmp", "--samples", "5", "--base", "main"]) == 0
    request = seen["request"]
    assert request.samples == 5
    assert request.base == "main"
    assert str(request.repo) == "/tmp"


def test_json_prints_the_run_payload(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    payload = {"verdict": "fail", "exit_code": 1}
    (tmp_path / "verdict.json").write_text(json.dumps(payload), encoding="utf-8")
    stub(monkeypatch, report(Verdict.FAIL, run_dir=tmp_path))
    assert cli.main(["review", "--json"]) == 1


def test_the_report_prints_every_finding(monkeypatch: pytest.MonkeyPatch,
                                         capsys: pytest.CaptureFixture[str]) -> None:
    finding = Finding(id="F-01", dimension="security", severity="critical",
                      state=State.PROVEN, location="a.py:2",
                      claim="A key is committed.", detail="a.py:2 is added by this change")
    stub(monkeypatch, report(Verdict.FAIL, findings=(finding,)))
    cli.main(["review"])
    out = capsys.readouterr().out
    assert "F-01" in out
    assert "a.py:2" in out
    assert "proven" in out


def test_the_run_id_is_passed_through(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, Any] = {}

    def capture(request: Any, runner: Any) -> Report:
        seen["request"] = request
        return report(Verdict.PASS)

    monkeypatch.setattr(cli, "review", capture)
    assert cli.main(["review", "--run-id", "abc"]) == 0
    assert seen["request"].run_id == "abc"


def test_verify_runs_the_registry_and_passes(tmp_path: Path) -> None:
    registry = tmp_path / "claims.toml"
    registry.write_text('[[claim]]\nid = "x"\ntext = "It holds."\ncheck = "true"\n',
                        encoding="utf-8")
    assert cli.main(["verify", "--registry", str(registry)]) == 0


def test_verify_fails_when_a_claim_is_false(tmp_path: Path) -> None:
    registry = tmp_path / "claims.toml"
    registry.write_text('[[claim]]\nid = "x"\ntext = "It does not."\ncheck = "false"\n',
                        encoding="utf-8")
    assert cli.main(["verify", "--registry", str(registry)]) == 1