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
    checks = doctor.run("council-generalist", runner=lambda prompt: "ok", binary="hermes")
    assert [check.status for check in checks] == ["ok", "fail", "ok", "ok"]


def test_a_profile_that_cannot_answer_is_a_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(doctor.shutil, "which",
                        which({"git": "/g", "hermes": "/h", "bwrap": "/b"}))

    def dead(prompt: str) -> str:
        raise TimeoutError("no answer")

    checks = doctor.run("council-generalist", runner=dead, probe_timeout=60)
    profile = next(check for check in checks if check.name == "profile")
    assert profile.status == "fail"
    assert "TimeoutError" in profile.detail


def test_a_profile_that_answers_is_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(doctor.shutil, "which",
                        which({"git": "/g", "hermes": "/h", "bwrap": "/b"}))
    checks = doctor.run("p", runner=lambda prompt: "ok", probe_timeout=60)
    profile = next(check for check in checks if check.name == "profile")
    assert profile.status == "ok"
    assert "answered in" in profile.detail


def test_bwrap_missing_is_a_warning_not_a_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(doctor.shutil, "which", which({"git": "/g", "hermes": "/h"}))
    checks = doctor.run("p", runner=lambda prompt: "ok")
    warnings = [check.name for check in checks if check.status == doctor.WARN]
    assert warnings == ["bwrap"]


def test_doctor_exits_1_when_a_check_fails(monkeypatch: pytest.MonkeyPatch,
                                           capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(doctor.shutil, "which", which({"git": "/g"}))
    monkeypatch.setattr("council.cli.hermes_runner", lambda *a, **k: (lambda prompt: "ok"))
    assert main(["doctor", "--json"]) == 1
    payload = json.loads(capsys.readouterr().out)
    assert any(item["status"] == "fail" for item in payload)


def test_doctor_exits_0_when_every_check_passes(monkeypatch: pytest.MonkeyPatch,
                                                capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(doctor.shutil, "which",
                        which({"git": "/g", "hermes": "/h", "bwrap": "/b"}))
    monkeypatch.setattr("council.cli.hermes_runner", lambda *a, **k: (lambda prompt: "ok"))
    assert main(["doctor"]) == 0
    out = capsys.readouterr().out
    assert "fail" not in out
    assert out.count("ok") >= 4
