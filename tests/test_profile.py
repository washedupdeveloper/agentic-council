"""The reviewer's own configuration is part of the instrument, not a detail.

The model, provider and reasoning default live in a Hermes profile this tool
does not parse, so the fingerprint is the bytes. These tests hold that shape: a
change is visible, a missing file is named rather than assumed unchanged, and a
profile name is never followed as a path.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from council.runner import ProfileFingerprint, hermes_home, profile_fingerprint

NAME = "council-generalist"


def profile_dir(home: Path, name: str = NAME) -> Path:
    directory = home / "profiles" / name
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def test_the_fingerprint_names_the_profile_configuration(tmp_path: Path,
                                                         monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    (profile_dir(tmp_path) / "config.yaml").write_text("model:\n  default: a\n", encoding="utf-8")
    fingerprint = profile_fingerprint(NAME)
    assert fingerprint.path == f"profiles/{NAME}/config.yaml"
    assert len(fingerprint.sha256) == 16


def test_a_changed_model_changes_the_fingerprint(tmp_path: Path,
                                                 monkeypatch: pytest.MonkeyPatch) -> None:
    """The whole point: same profile name, different model, different instrument."""
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    config = profile_dir(tmp_path) / "config.yaml"
    config.write_text("model:\n  default: a\n", encoding="utf-8")
    before = profile_fingerprint(NAME)
    config.write_text("model:\n  default: b\n", encoding="utf-8")
    assert profile_fingerprint(NAME) != before


def test_both_configuration_files_are_covered(tmp_path: Path,
                                              monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    directory = profile_dir(tmp_path)
    (directory / "config.yaml").write_text("model:\n  default: a\n", encoding="utf-8")
    persona = directory / "profile.yaml"
    persona.write_text("name: council-generalist\n", encoding="utf-8")
    before = profile_fingerprint(NAME)
    persona.write_text("name: someone-else\n", encoding="utf-8")
    assert profile_fingerprint(NAME) != before


def test_a_missing_profile_is_reported_as_missing(tmp_path: Path,
                                                   monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    assert profile_fingerprint("nobody") == ProfileFingerprint()


def test_a_profile_name_that_is_a_path_is_not_read(tmp_path: Path,
                                                    monkeypatch: pytest.MonkeyPatch) -> None:
    home = tmp_path / "home"
    (home / "profiles").mkdir(parents=True)
    monkeypatch.setenv("HERMES_HOME", str(home))
    (tmp_path / "outside.yaml").write_text("model: secret\n", encoding="utf-8")
    assert profile_fingerprint("../outside") == ProfileFingerprint()


def test_the_home_is_the_environment_when_it_is_set(tmp_path: Path,
                                                     monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    assert hermes_home() == tmp_path


def test_a_host_without_a_home_has_no_fingerprint(monkeypatch: pytest.MonkeyPatch) -> None:
    """`Path.home()` raises when HOME cannot be resolved; a review must still start."""
    def boom() -> Path:
        raise RuntimeError("no home")

    monkeypatch.setattr("council.runner.hermes_home", boom)
    assert profile_fingerprint(NAME) == ProfileFingerprint()
