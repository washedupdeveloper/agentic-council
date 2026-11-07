"""The CLI is a thin adapter: parse, call, map the verdict to an exit code."""

from __future__ import annotations

import json
import subprocess
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


def test_the_reviewer_binary_is_passed_through(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, Any] = {}

    def fake_runner(profile: str, **kwargs: Any) -> Any:
        seen["profile"] = profile
        seen.update(kwargs)
        return lambda prompt: "{}"

    monkeypatch.setattr(cli, "hermes_runner", fake_runner)
    stub(monkeypatch, report(Verdict.PASS))
    assert cli.main(["review", "--reviewer", "/bin/other"]) == 0
    assert seen["binary"] == "/bin/other"


def test_init_adds_the_state_directory(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    assert cli.main(["init", "-C", str(tmp_path)]) == 0
    assert ".council/" in (tmp_path / ".gitignore").read_text(encoding="utf-8")


def test_verify_writes_and_checks_the_page(tmp_path: Path) -> None:
    registry = tmp_path / "claims.toml"
    registry.write_text('[[claim]]\nid = "x"\ntext = "It holds."\ncheck = "true"\n',
                        encoding="utf-8")
    page = tmp_path / "CLAIMS.md"
    assert cli.main(["verify", "--registry", str(registry), "--write", str(page)]) == 0
    assert cli.main(["verify", "--registry", str(registry), "--check", str(page)]) == 0


def test_a_bad_config_is_a_start_failure(tmp_path: Path,
                                         monkeypatch: pytest.MonkeyPatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    for argv in (["init", "-q"], ["config", "user.email", "t@e.invalid"],
                 ["config", "user.name", "t"]):
        subprocess.run(["git", *argv], cwd=repo, check=True)
    (repo / "a.py").write_text("x = 1\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-qm", "one"], cwd=repo, check=True)
    (repo / "a.py").write_text("x = 1\ny = 2\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-qm", "two"], cwd=repo, check=True)
    (repo / "council.toml").write_text('[proofs]\nallows = ["rg"]\n', encoding="utf-8")

    empty = json.dumps({"sections": {name: [] for name in ("security", "correctness",
                                                           "readability", "architecture",
                                                           "performance")}})
    monkeypatch.setattr(cli, "hermes_runner", lambda *a, **k: (lambda prompt: empty))
    assert cli.main(["review", "-C", str(repo), "--run-id", "cfg", "--report"]) == 3


def test_verify_with_a_missing_registry_is_not_incomplete(tmp_path: Path) -> None:
    """2 means a review is incomplete; a registry that cannot be read is 3."""
    assert cli.main(["verify", "--registry", str(tmp_path / "nope.toml")]) == 3


def test_verify_fails_when_a_claim_is_false(tmp_path: Path) -> None:
    registry = tmp_path / "claims.toml"
    registry.write_text('[[claim]]\nid = "x"\ntext = "It does not."\ncheck = "false"\n',
                        encoding="utf-8")
    assert cli.main(["verify", "--registry", str(registry)]) == 1