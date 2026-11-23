"""council doctor: what this machine can do, measured."""

from __future__ import annotations

import json

import pytest

from council import doctor
from council.cli import main


def which(paths: dict[str, str]):  # type: ignore[no-untyped-def]
    return lambda name: paths.get(name)


def test_a_missing_reviewer_binary_is_a_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(doctor.shutil, "which",
                        which({"git": "/usr/bin/git", "bwrap": "/usr/bin/bwrap"}))
    checks = doctor.run("hermes", runner=lambda prompt: "ok", binary="hermes")
    assert [check.status for check in checks] == ["ok", "fail", "ok", "ok"]


def test_a_profile_that_cannot_answer_is_a_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(doctor.shutil, "which",
                        which({"git": "/g", "hermes": "/h", "bwrap": "/b"}))

    def dead(prompt: str) -> str:
        raise TimeoutError("no answer")

    checks = doctor.run("hermes", runner=dead, probe_timeout=60)
    profile = next(check for check in checks if check.name == "agent")
    assert profile.status == "fail"
    assert "TimeoutError" in profile.detail


def test_a_profile_that_answers_is_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(doctor.shutil, "which",
                        which({"git": "/g", "hermes": "/h", "bwrap": "/b"}))
    checks = doctor.run("hermes", runner=lambda prompt: "ok", probe_timeout=60)
    profile = next(check for check in checks if check.name == "agent")
    assert profile.status == "ok"
    assert "answered in" in profile.detail


def test_a_profile_that_returns_nothing_is_a_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(doctor.shutil, "which",
                        which({"git": "/g", "hermes": "/h", "bwrap": "/b"}))
    checks = doctor.run("hermes", runner=lambda prompt: "   ", probe_timeout=60)
    profile = next(check for check in checks if check.name == "agent")
    assert profile.status == "fail"
    assert "returned nothing" in profile.detail


def test_a_doctor_line_does_not_emit_terminal_controls() -> None:
    check = doctor.Check("profile", "fail", "p\x1b[31mred\nline")
    assert "\x1b" not in check.line()
    assert "\n" not in check.line()


def test_bwrap_missing_is_a_warning_not_a_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(doctor.shutil, "which", which({"git": "/g", "hermes": "/h"}))
    checks = doctor.run("hermes", runner=lambda prompt: "ok")
    warnings = [check.name for check in checks if check.status == doctor.WARN]
    assert warnings == ["bwrap"]


def test_doctor_exits_1_when_a_check_fails(monkeypatch: pytest.MonkeyPatch,
                                           capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(doctor.shutil, "which", which({"git": "/g"}))
    monkeypatch.setattr("council.cli._agent_runner", lambda args, **kwargs: (lambda prompt: "ok"))
    assert main(["doctor", "--json"]) == 1
    payload = json.loads(capsys.readouterr().out)
    assert any(item["status"] == "fail" for item in payload)


def test_doctor_exits_0_when_every_check_passes(monkeypatch: pytest.MonkeyPatch,
                                                capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(doctor.shutil, "which",
                        which({"git": "/g", "hermes": "/h", "bwrap": "/b"}))
    monkeypatch.setattr("council.cli._agent_runner", lambda args, **kwargs: (lambda prompt: "ok"))
    assert main(["doctor"]) == 0
    out = capsys.readouterr().out
    assert "fail" not in out
    assert out.count("ok") >= 4


def test_doctor_reports_a_matching_source_version(
        tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "pyproject.toml").write_text('[project]\nversion = "2.0.0"\n',
                                              encoding="utf-8")
    monkeypatch.setattr(doctor, "current_version", lambda: "2.0.0")
    check = doctor.check_source(tmp_path)
    assert check is not None
    assert check.status == "ok"


def test_doctor_reports_a_source_version_mismatch(
        tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "pyproject.toml").write_text('[project]\nversion = "2.0.0"\n',
                                              encoding="utf-8")
    monkeypatch.setattr(doctor, "current_version", lambda: "1.9.0")
    check = doctor.check_source(tmp_path)
    assert check is not None
    assert check.status == "fail"
    assert "1.9.0" in check.detail and "2.0.0" in check.detail


def test_doctor_refuses_a_source_without_a_version(
        tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname = \"council\"\n",
                                              encoding="utf-8")
    monkeypatch.setattr(doctor, "current_version", lambda: "2.0.0")
    check = doctor.check_source(tmp_path)
    assert check is not None
    assert check.status == "fail"
    assert "cannot read project.version" in check.detail


def test_doctor_does_not_claim_a_source_run_matches(
        tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "pyproject.toml").write_text('[project]\nversion = "2.0.0"\n',
                                              encoding="utf-8")
    monkeypatch.setattr(doctor, "current_version", lambda: doctor.SOURCE_VERSION)
    check = doctor.check_source(tmp_path)
    assert check is not None
    assert check.status == "warn"
    assert "no installed version" in check.detail
