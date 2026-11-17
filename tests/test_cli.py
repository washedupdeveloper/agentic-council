"""The CLI is a thin adapter: parse, call, map the verdict to an exit code."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

import council.cli as cli
from council.domain.findings import Finding, State
from council.domain.baseline import GateResult
from council.domain.scope import ScopeIgnored
from council.repo import Skipped
from council.run import PromptTooLarge, Report, ReviewError
from council.domain.verdict import Result, Verdict


def report(verdict: Verdict, *, run_dir: Path | None = None,
           findings: tuple[Finding, ...] = (),
           skipped: tuple[Skipped, ...] = (),
           gate: GateResult | None = None) -> Report:
    return Report(
        run_dir=run_dir or Path("/nonexistent"),
        base="a" * 40,
        head="b" * 40,
        digest="d" * 16,
        result=Result(verdict, "a reason", findings),
        samples=(),
        skipped=skipped,
        gate=gate,
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


def test_incomplete_is_announced_explicitly(monkeypatch: pytest.MonkeyPatch,
                                            capsys: pytest.CaptureFixture[str]) -> None:
    stub(monkeypatch, report(Verdict.INCOMPLETE))
    cli.main(["review"])
    err = capsys.readouterr().err
    assert "INCOMPLETE" in err
    assert "blocked" in err


def test_a_file_the_diff_could_not_carry_is_announced(monkeypatch: pytest.MonkeyPatch,
                                                      capsys: pytest.CaptureFixture[str]) -> None:
    stub(monkeypatch, report(Verdict.PASS, skipped=(Skipped("logo.bin", "binary"),)))
    cli.main(["review"])
    err = capsys.readouterr().err
    assert "not reviewed" in err
    assert "logo.bin" in err


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


def test_ci_reads_a_baseline_from_the_base_revision_by_default() -> None:
    parser = cli.build_parser()
    assert parser.parse_args(["ci", "--baseline", ".council/baseline.json"]).baseline_from_base
    assert not parser.parse_args(["review", "--baseline", "baseline.json"]).baseline_from_base


def test_baseline_create_requires_an_owner() -> None:
    with pytest.raises(SystemExit) as raised:
        cli.main(["baseline", "create", "--from", "/tmp/run", "--out", "/tmp/b.json"])
    assert raised.value.code == 3


def test_baseline_flags_reach_the_request(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, object] = {}

    def capture(request: Any, runner: Any) -> Report:
        seen["baseline"] = request.baseline
        seen["strict"] = request.baseline_strict
        return report(Verdict.PASS)

    monkeypatch.setattr(cli, "review", capture)
    assert cli.main(["review", "--baseline", "baseline.json", "--baseline-strict"]) == 0
    assert seen == {"baseline": Path("baseline.json"), "strict": True}


def test_scope_and_staged_flags_reach_the_request(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, object] = {}

    def capture(request: Any, runner: Any) -> Report:
        seen["include"] = request.include
        seen["exclude"] = request.exclude
        seen["staged"] = request.staged
        return report(Verdict.PASS)

    monkeypatch.setattr(cli, "review", capture)
    assert cli.main(["review", "--include", "src/**", "--exclude", "src/generated/**",
                     "--staged"]) == 0
    assert seen == {"include": ("src/**",), "exclude": ("src/generated/**",),
                    "staged": True}


def test_a_bad_scope_pattern_is_a_start_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    called: list[object] = []

    def capture(request: Any, runner: Any) -> Report:
        called.append(request)
        return report(Verdict.PASS)

    monkeypatch.setattr(cli, "review", capture)
    assert cli.main(["review", "--include", "/absolute"]) == 3
    assert called == []


def test_pr_does_not_expose_staged() -> None:
    parser = cli.build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["pr", "1", "--staged"])


def test_a_baselined_finding_is_not_a_sarif_alert(tmp_path: Path,
                                                  monkeypatch: pytest.MonkeyPatch) -> None:
    item = Finding("F-01", "security", "high", State.PROVEN, "a.py:2",
                   "A claim.", "detail", "proof")
    gate = GateResult(Verdict.PASS, "baselined", suppressed=("F-01",), entries=1)
    monkeypatch.setattr(cli, "review",
                        lambda request, runner: report(Verdict.FAIL, findings=(item,),
                                                        gate=gate))
    path = tmp_path / "council.sarif"
    assert cli.main(["review", "--sarif", str(path)]) == 0
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["runs"][0]["results"] == []


def test_the_context_urls_are_passed_through(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, tuple[str, ...]] = {}

    def capture(request: Any, runner: Any) -> Report:
        seen["urls"] = request.context_urls
        return report(Verdict.PASS)

    monkeypatch.setattr(cli, "review", capture)
    assert cli.main(["review", "--context-url", "https://example.invalid/a",
                     "--context-url", "https://example.invalid/b"]) == 0
    assert seen["urls"] == ("https://example.invalid/a", "https://example.invalid/b")


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


def test_the_human_report_does_not_emit_terminal_controls(
        monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    finding = Finding(id="F-01", dimension="security", severity="critical",
                      state=State.PROVEN, location="a.py:2",
                      claim="A\x1b[31mred\nclaim", detail="bad\x07detail")
    stub(monkeypatch, report(Verdict.FAIL, findings=(finding,)))
    cli.main(["review"])
    out = capsys.readouterr().out
    assert "\x1b" not in out
    assert "\x07" not in out


def test_the_run_id_is_passed_through(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, Any] = {}

    def capture(request: Any, runner: Any) -> Report:
        seen["request"] = request
        return report(Verdict.PASS)

    monkeypatch.setattr(cli, "review", capture)
    assert cli.main(["review", "--run-id", "abc"]) == 0
    assert seen["request"].run_id == "abc"


def test_ci_prints_the_verdict_as_json_and_exits_with_it(monkeypatch: pytest.MonkeyPatch,
                                                         tmp_path: Path,
                                                         capsys: pytest.CaptureFixture[str]) -> None:
    payload = {"verdict": "fail", "exit_code": 1}
    (tmp_path / "verdict.json").write_text(json.dumps(payload), encoding="utf-8")
    stub(monkeypatch, report(Verdict.FAIL, run_dir=tmp_path))
    assert cli.main(["ci"]) == 1
    assert json.loads(capsys.readouterr().out) == payload


def test_ci_has_no_advice_switch() -> None:
    """A gate that can be told to exit 0 is not a gate."""
    with pytest.raises(SystemExit) as raised:
        cli.main(["ci", "--report"])
    assert raised.value.code == 3


def test_verify_is_not_a_subcommand() -> None:
    """The registry is the maintainer's entry point: council-verify."""
    with pytest.raises(SystemExit) as raised:
        cli.main(["verify"])
    assert raised.value.code == 3


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


def test_the_sample_timeout_reaches_the_runner(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, Any] = {}

    def fake_runner(profile: str, **kwargs: Any) -> Any:
        seen.update(kwargs)
        return lambda prompt: "{}"

    monkeypatch.setattr(cli, "hermes_runner", fake_runner)
    stub(monkeypatch, report(Verdict.PASS))
    assert cli.main(["review", "--sample-timeout", "120"]) == 0
    assert seen["timeout"] == 120


def test_the_reasoning_level_reaches_the_runner(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, Any] = {}

    def fake_runner(profile: str, **kwargs: Any) -> Any:
        seen.update(kwargs)
        return lambda prompt: "{}"

    monkeypatch.setattr(cli, "hermes_runner", fake_runner)
    stub(monkeypatch, report(Verdict.PASS))
    assert cli.main(["review", "--reasoning", "none"]) == 0
    assert seen["reasoning"] == "none"


def test_streaming_is_on_by_default_and_can_be_turned_off(
        monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[dict[str, Any]] = []

    def fake_runner(profile: str, **kwargs: Any) -> Any:
        seen.append(kwargs)
        return lambda prompt: "{}"

    monkeypatch.setattr(cli, "hermes_runner", fake_runner)
    stub(monkeypatch, report(Verdict.PASS))
    assert cli.main(["review", "--run-id", "one"]) == 0
    assert cli.main(["review", "--no-stream", "--run-id", "two"]) == 0
    assert seen[0]["stream"] is True
    assert seen[0]["idle_timeout"] == 120
    assert seen[1]["stream"] is False


def test_the_version_is_reported(capsys: pytest.CaptureFixture[str]) -> None:
    import council

    with pytest.raises(SystemExit) as stopped:
        cli.main(["--version"])
    assert stopped.value.code == 0
    assert council.__version__ in capsys.readouterr().out


def test_sarif_is_written_when_asked(tmp_path: Path,
                                     monkeypatch: pytest.MonkeyPatch) -> None:
    finding = Finding("F-01", "readability", "low", State.PROVEN, "a.py:2",
                      "A claim.", "A detail.")
    stub(monkeypatch, report(Verdict.PASS, findings=(finding,)))
    path = tmp_path / "council.sarif"
    assert cli.main(["review", "--sarif", str(path), "--run-id", "sarif"]) == 0
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["runs"][0]["results"][0]["ruleId"] == "readability"


def test_plan_prints_and_writes_nothing(monkeypatch: pytest.MonkeyPatch,
                                        capsys: pytest.CaptureFixture[str]) -> None:
    planned = cli.Plan("a" * 40, "b" * 40, 1234, 32768, False, (), (), 3)
    monkeypatch.setattr(cli, "plan", lambda request: planned)
    assert cli.main(["review", "--plan", "--base", "HEAD"]) == 0
    out = capsys.readouterr().out
    assert "PLAN" in out
    assert "1,234" in out


def test_plan_names_paths_outside_the_scope(monkeypatch: pytest.MonkeyPatch,
                                            capsys: pytest.CaptureFixture[str]) -> None:
    planned = cli.Plan(
        "a" * 40, "b" * 40, 1234, 32768, False, (), (), 3,
        scope_ignored=(ScopeIgnored("docs/b.md", "outside include"),),
        scope_include=("src/**",),
    )
    monkeypatch.setattr(cli, "plan", lambda request: planned)
    assert cli.main(["review", "--plan", "--base", "HEAD"]) == 0
    out = capsys.readouterr().out
    assert "outside scope" in out
    assert "docs/b.md" in out
    payload = cli._plan_payload(planned)  # noqa: SLF001 - asserting the JSON contract
    assert payload["scope"] == {"include": ["src/**"], "exclude": []}
    assert payload["scope_ignored"] == [
        {"path": "docs/b.md", "reason": "outside include", "pattern": None},
    ]
    assert cli.main(["review", "--plan", "--json", "--base", "HEAD"]) == 0
    emitted = json.loads(capsys.readouterr().out)
    assert emitted["scope_ignored"] == payload["scope_ignored"]


def test_pr_takes_its_base_from_github_and_records_it(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    pull = cli.PullRequest(7, "https://example/7", "A change", "a" * 40, "b" * 40,
                           "main", "topic")
    monkeypatch.setattr(cli, "resolve_pr", lambda number, repo: pull)
    monkeypatch.setattr(cli, "verify_checkout", lambda pr, repo: None)
    seen: dict[str, object] = {}

    def fake_review(request: object, runner: object) -> Report:
        seen["request"] = request
        return report(Verdict.PASS)

    monkeypatch.setattr(cli, "review", fake_review)
    assert cli.main(["pr", "7", "-C", str(tmp_path), "--run-id", "pr"]) == 0
    request = seen["request"]
    assert getattr(request, "base") == "a" * 40
    assert getattr(request, "pull_request") == pull


def test_pr_does_not_accept_a_base() -> None:
    with pytest.raises(SystemExit) as stopped:
        cli.main(["pr", "7", "--base", "main"])
    assert stopped.value.code == 3


def test_ephemeral_removes_the_run_after_the_verdict(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "ephemeral"
    monkeypatch.setattr(cli.tempfile, "mkdtemp", lambda prefix: str(root))

    def fake_review(request: object, runner: object) -> Report:
        run = request.state_dir  # type: ignore[attr-defined]
        run.mkdir(parents=True)
        (run / "verdict.json").write_text("{}", encoding="utf-8")
        return Report(run, "a" * 40, "b" * 40, "d" * 16,
                      Result(Verdict.PASS, "ok", ()), ())

    monkeypatch.setattr(cli, "review", fake_review)
    assert cli.main(["review", "--ephemeral", "--run-id", "e"]) == 0
    assert not root.exists()


def test_review_is_ephemeral_by_default(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "default-eph"
    monkeypatch.setattr(cli.tempfile, "mkdtemp", lambda prefix: str(root))

    def fake_review(request: object, runner: object) -> Report:
        run = request.state_dir  # type: ignore[attr-defined]
        assert run is not None
        run.mkdir(parents=True)
        (run / "verdict.json").write_text("{}", encoding="utf-8")
        return Report(run, "a" * 40, "b" * 40, "d" * 16,
                      Result(Verdict.PASS, "ok", ()), ())

    monkeypatch.setattr(cli, "review", fake_review)
    assert cli.main(["review", "--run-id", "d"]) == 0
    assert not root.exists()


def test_no_ephemeral_keeps_state_in_the_repository(
        monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, object] = {}

    def fake_review(request: object, runner: object) -> Report:
        seen["state"] = request.state_dir  # type: ignore[attr-defined]
        return report(Verdict.PASS)

    monkeypatch.setattr(cli, "review", fake_review)
    assert cli.main(["review", "--no-ephemeral"]) == 0
    assert seen["state"] is None


@pytest.mark.parametrize("run_id", ["", "   ", "../escape", "/tmp/escape", "a/b",
                                    "a\\b", "a:b", "a?b", "a*b", "a|b", "a<b",
                                    "a>b", 'a"b', "a\nb", "a\0b", "x" * 129])
def test_an_invalid_run_id_is_refused_before_a_run(
        monkeypatch: pytest.MonkeyPatch, run_id: str) -> None:
    called: list[int] = []

    def fake_review(request: object, runner: object) -> Report:
        called.append(1)
        return report(Verdict.PASS)

    monkeypatch.setattr(cli, "review", fake_review)
    assert cli.main(["review", "--run-id", run_id]) == 3
    assert called == []


def test_time_budget_zero_is_valid(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, int] = {}

    def fake_review(request: object, runner: object) -> Report:
        seen["budget"] = request.time_budget  # type: ignore[attr-defined]
        return report(Verdict.PASS)

    monkeypatch.setattr(cli, "review", fake_review)
    assert cli.main(["review", "--time-budget", "0"]) == 0
    assert seen["budget"] == 0


def test_plan_refuses_outputs_it_cannot_write(tmp_path: Path) -> None:
    assert cli.main(["review", "--plan", "--sarif", str(tmp_path / "x.sarif")]) == 3
    assert cli.main(["review", "--plan", "--keep", str(tmp_path)]) == 3
    assert cli.main(["review", "--plan", "--report"]) == 3
    assert cli.main(["review", "--plan", "--run-id", "../escape"]) == 3


def test_a_sarif_parent_that_does_not_exist_is_refused_before_a_run(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    called: list[int] = []

    def fake_review(request: object, runner: object) -> Report:
        called.append(1)
        return report(Verdict.PASS)

    monkeypatch.setattr(cli, "review", fake_review)
    path = tmp_path / "missing" / "council.sarif"
    assert cli.main(["review", "--sarif", str(path)]) == 3
    assert called == []


def test_a_keep_path_that_is_a_file_is_refused_before_a_run(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    called: list[int] = []

    def fake_review(request: object, runner: object) -> Report:
        called.append(1)
        return report(Verdict.PASS)

    monkeypatch.setattr(cli, "review", fake_review)
    keep = tmp_path / "keep"
    keep.write_text("not a directory", encoding="utf-8")
    assert cli.main(["review", "--keep", str(keep)]) == 3
    assert called == []


def test_a_prompt_directory_is_refused_before_a_run(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    called: list[int] = []

    def fake_review(request: object, runner: object) -> Report:
        called.append(1)
        return report(Verdict.PASS)

    monkeypatch.setattr(cli, "review", fake_review)
    prompt = tmp_path / "prompt.md"
    prompt.mkdir()
    assert cli.main(["review", "--prompt", str(prompt)]) == 3
    assert called == []


def test_a_json_read_failure_removes_the_ephemeral_tree(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "ephemeral"
    monkeypatch.setattr(cli.tempfile, "mkdtemp", lambda prefix: str(root))

    def fake_review(request: object, runner: object) -> Report:
        return report(Verdict.PASS, run_dir=tmp_path / "missing")

    monkeypatch.setattr(cli, "review", fake_review)
    assert cli.main(["review", "--json", "--run-id", "x"]) == 3
    assert not root.exists()


def test_keep_inside_the_run_directory_is_refused(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "ephemeral"
    run = tmp_path / "run"
    monkeypatch.setattr(cli.tempfile, "mkdtemp", lambda prefix: str(root))

    def fake_review(request: object, runner: object) -> Report:
        root.mkdir(parents=True, exist_ok=True)
        run.mkdir()
        (run / "verdict.json").write_text("{}", encoding="utf-8")
        return Report(run, "a" * 40, "b" * 40, "d" * 16,
                      Result(Verdict.PASS, "ok", ()), ())

    monkeypatch.setattr(cli, "review", fake_review)
    assert cli.main(["review", "--keep", str(tmp_path), "--run-id", "x"]) == 0
    assert root.exists()
    shutil.rmtree(root)


def test_keep_refuses_an_existing_target(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "ephemeral"
    run = tmp_path / "run"
    keep = tmp_path / "kept"
    keep.mkdir()
    (keep / "run").mkdir()
    monkeypatch.setattr(cli.tempfile, "mkdtemp", lambda prefix: str(root))

    def fake_review(request: object, runner: object) -> Report:
        root.mkdir(parents=True, exist_ok=True)
        run.mkdir()
        (run / "verdict.json").write_text("{}", encoding="utf-8")
        return Report(run, "a" * 40, "b" * 40, "d" * 16,
                      Result(Verdict.PASS, "ok", ()), ())

    monkeypatch.setattr(cli, "review", fake_review)
    assert cli.main(["review", "--keep", str(keep), "--run-id", "run"]) == 0
    assert root.exists()
    assert not (keep / "run" / "verdict.json").exists()
    shutil.rmtree(root)


def test_keep_copies_the_run_before_removing_it(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "ephemeral"
    keep = tmp_path / "kept"
    monkeypatch.setattr(cli.tempfile, "mkdtemp", lambda prefix: str(root))

    def fake_review(request: object, runner: object) -> Report:
        run = request.state_dir  # type: ignore[attr-defined]
        run.mkdir(parents=True)
        (run / "verdict.json").write_text("{}", encoding="utf-8")
        return Report(run, "a" * 40, "b" * 40, "d" * 16,
                      Result(Verdict.PASS, "ok", ()), ())

    monkeypatch.setattr(cli, "review", fake_review)
    assert cli.main(["review", "--keep", str(keep), "--run-id", "k"]) == 0
    assert (keep / "k" / "verdict.json").is_file()
    assert not root.exists()


def test_the_sandbox_defaults_on_when_bwrap_exists_and_can_be_disabled(
        monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli.shutil, "which",
                        lambda name: "/usr/bin/bwrap" if name == "bwrap" else None)
    seen: list[bool] = []

    def fake_review(request: object, runner: object) -> Report:
        seen.append(request.sandbox)  # type: ignore[attr-defined]
        return report(Verdict.PASS)

    monkeypatch.setattr(cli, "review", fake_review)
    assert cli.main(["review"]) == 0
    assert cli.main(["review", "--no-sandbox"]) == 0
    assert seen == [True, False]


def test_init_adds_the_state_directory(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    assert cli.main(["init", "-C", str(tmp_path)]) == 0
    assert ".council/" in (tmp_path / ".gitignore").read_text(encoding="utf-8")


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


class _Stdin:
    """A terminal that answers from a script."""

    def __init__(self, lines: list[str], *, tty: bool = True) -> None:
        self._lines = list(lines)
        self._tty = tty

    def isatty(self) -> bool:
        return self._tty

    def readline(self) -> str:
        return self._lines.pop(0) if self._lines else ""


class _NoRead(_Stdin):
    def readline(self) -> str:
        raise AssertionError("this path must not read stdin")


def _oversize() -> PromptTooLarge:
    return PromptTooLarge(60_000, 32_768)


def test_ci_refuses_an_oversized_prompt_without_reading_input(
        monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    def boom(request: Any, runner: Any) -> Report:
        raise _oversize()

    monkeypatch.setattr(cli, "review", boom)
    monkeypatch.setattr(cli.sys, "stdin", _NoRead([]))
    assert cli.main(["ci"]) == 3
    err = capsys.readouterr().err
    assert "60,000" in err and "allow-large-prompt" in err


def test_review_asks_and_allow_sends_it(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[Any] = []

    def fake(request: Any, runner: Any) -> Report:
        calls.append(request)
        if len(calls) == 1:
            raise _oversize()
        return report(Verdict.PASS)

    monkeypatch.setattr(cli, "review", fake)
    monkeypatch.setattr(cli.sys, "stdin", _Stdin(["allow\n"]))
    assert cli.main(["review"]) == 0
    assert calls[1].allow_large_prompt is True


def test_review_asks_and_window_splits_it(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[Any] = []

    def fake(request: Any, runner: Any) -> Report:
        calls.append(request)
        if len(calls) == 1:
            raise PromptTooLarge(60_000, 32_768, unit="a.py", windows=4)
        return report(Verdict.PASS)

    monkeypatch.setattr(cli, "review", fake)
    monkeypatch.setattr(cli.sys, "stdin", _Stdin(["window\n"]))
    assert cli.main(["review"]) == 0
    assert calls[1].window_large_files is True
    assert calls[1].max_windows == 200


def test_the_window_answer_is_refused_when_nothing_can_be_split(
        monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    """A prompt over the limit for no splittable reason must not offer the choice."""

    def boom(request: Any, runner: Any) -> Report:
        raise PromptTooLarge(60_000, 32_768)

    monkeypatch.setattr(cli, "review", boom)
    monkeypatch.setattr(cli.sys, "stdin", _Stdin(["window\n", "cancel\n"]))
    assert cli.main(["review"]) == 3
    assert "not available" in capsys.readouterr().err


def test_review_can_raise_the_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[Any] = []

    def fake(request: Any, runner: Any) -> Report:
        calls.append(request)
        if len(calls) == 1:
            raise _oversize()
        return report(Verdict.PASS)

    monkeypatch.setattr(cli, "review", fake)
    monkeypatch.setattr(cli.sys, "stdin", _Stdin(["budget 999999\n"]))
    assert cli.main(["review"]) == 0
    assert calls[1].max_prompt_bytes == 999999


def test_review_can_narrow_the_base(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[Any] = []

    def fake(request: Any, runner: Any) -> Report:
        calls.append(request)
        if len(calls) == 1:
            raise _oversize()
        return report(Verdict.PASS)

    monkeypatch.setattr(cli, "review", fake)
    monkeypatch.setattr(cli.sys, "stdin", _Stdin(["base HEAD~4\n"]))
    assert cli.main(["review"]) == 0
    assert calls[1].base == "HEAD~4"


def test_review_can_lower_the_context_depth(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[Any] = []

    def fake(request: Any, runner: Any) -> Report:
        calls.append(request)
        if len(calls) == 1:
            raise _oversize()
        return report(Verdict.PASS)

    monkeypatch.setattr(cli, "review", fake)
    monkeypatch.setattr(cli.sys, "stdin", _Stdin(["context 1\n"]))
    assert cli.main(["review"]) == 0
    assert calls[1].context_depth == 1


def test_silence_cancels_and_sends_nothing(monkeypatch: pytest.MonkeyPatch,
                                          capsys: pytest.CaptureFixture[str]) -> None:
    def fake(request: Any, runner: Any) -> Report:
        raise _oversize()

    monkeypatch.setattr(cli, "review", fake)
    monkeypatch.setattr(cli.sys, "stdin", _Stdin([]))
    assert cli.main(["review"]) == 3
    assert "declined" in capsys.readouterr().err


def test_autonomous_refuses_without_asking(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(request: Any, runner: Any) -> Report:
        raise _oversize()

    monkeypatch.setattr(cli, "review", boom)
    monkeypatch.setattr(cli.sys, "stdin", _NoRead([]))
    assert cli.main(["review", "--autonomous"]) == 3


def test_a_question_is_answered_before_a_decision(monkeypatch: pytest.MonkeyPatch,
                                                  capsys: pytest.CaptureFixture[str]) -> None:
    def boom(request: Any, runner: Any) -> Report:
        raise _oversize()

    monkeypatch.setattr(cli, "review", boom)
    monkeypatch.setattr(cli.sys, "stdin", _Stdin(["?\n", "cancel\n"]))
    assert cli.main(["review"]) == 3
    assert "why there is a limit" in capsys.readouterr().err
