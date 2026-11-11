"""Configuration: defaults when absent, and a refusal for every key that does nothing."""

from __future__ import annotations

from pathlib import Path

import pytest

from council.config import DEFAULT_ALLOW, ConfigError, Policy, load


def write(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "council.toml"
    path.write_text(body, encoding="utf-8")
    return path


def test_a_missing_file_means_the_defaults(tmp_path: Path) -> None:
    config = load(tmp_path / "council.toml")
    assert config.allow == DEFAULT_ALLOW
    assert config.timeout == 120


def test_an_explicit_allowlist_replaces_the_default(tmp_path: Path) -> None:
    config = load(write(tmp_path, '[proofs]\nallow = ["rg", "git"]\ntimeout = 30\n'))
    assert config.allow == frozenset({"rg", "git"})
    assert config.timeout == 30


def test_an_unknown_top_level_key_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="unknown key"):
        load(write(tmp_path, "[profs]\nallow = []\n"))


def test_an_unknown_proofs_key_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="unknown key"):
        load(write(tmp_path, "[proofs]\nallows = []\n"))


def test_a_misspelt_allow_is_an_error_not_a_default(tmp_path: Path) -> None:
    """The failure this prevents: a typo silently restoring the default allowlist."""
    with pytest.raises(ConfigError):
        load(write(tmp_path, '[proofs]\nallows = ["curl"]\n'))


def test_a_non_list_allow_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="list"):
        load(write(tmp_path, '[proofs]\nallow = "rg"\n'))


def test_the_sandbox_is_on_by_default(tmp_path: Path) -> None:
    assert load(tmp_path / "council.toml").sandbox is True


def test_the_sandbox_can_be_turned_off_when_the_caller_allows_it(tmp_path: Path) -> None:
    assert load(write(tmp_path, "[proofs]\nsandbox = false\n"),
                Policy(sandbox=False)).sandbox is False


def test_a_repository_cannot_turn_the_sandbox_off(tmp_path: Path) -> None:
    """The repository is untrusted: the boundary is the caller's, not its own."""
    with pytest.raises(ConfigError, match="requires the sandbox"):
        load(write(tmp_path, "[proofs]\nsandbox = false\n"))


def test_a_repository_cannot_add_a_tool(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="does not permit"):
        load(write(tmp_path, '[proofs]\nallow = ["rg", "cargo"]\n'))


def test_a_repository_can_narrow_the_allowlist(tmp_path: Path) -> None:
    assert load(write(tmp_path, '[proofs]\nallow = ["rg"]\n')).allow == frozenset({"rg"})


def test_a_repository_cannot_raise_the_timeout(tmp_path: Path) -> None:
    assert load(write(tmp_path, "[proofs]\ntimeout = 900\n")).timeout == 120


def test_a_repository_can_lower_the_timeout(tmp_path: Path) -> None:
    assert load(write(tmp_path, "[proofs]\ntimeout = 30\n")).timeout == 30


def test_a_non_boolean_sandbox_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="sandbox"):
        load(write(tmp_path, '[proofs]\nsandbox = "no"\n'))


def test_a_non_positive_timeout_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="positive"):
        load(write(tmp_path, "[proofs]\ntimeout = 0\n"))


def test_a_boolean_timeout_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="positive"):
        load(write(tmp_path, "[proofs]\ntimeout = true\n"))


def test_malformed_toml_is_a_config_error(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="not valid TOML"):
        load(write(tmp_path, "[proofs\nallow = []\n"))


def test_a_directory_is_a_config_error(tmp_path: Path) -> None:
    path = tmp_path / "council.toml"
    path.mkdir()
    with pytest.raises(ConfigError, match="regular file"):
        load(path)


def test_a_non_utf8_config_is_a_config_error(tmp_path: Path) -> None:
    path = tmp_path / "council.toml"
    path.write_bytes(b"\xff\xfe")
    with pytest.raises(ConfigError, match="UTF-8"):
        load(path)


def test_a_broken_symlink_is_a_config_error(tmp_path: Path) -> None:
    path = tmp_path / "council.toml"
    path.symlink_to(tmp_path / "missing.toml")
    with pytest.raises(ConfigError, match="broken symlink"):
        load(path)
