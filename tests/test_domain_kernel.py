"""The pure kernel: decisions from literals, with no fixture, server or spawn."""

from __future__ import annotations

from pathlib import Path

import pytest

from council.domain.adjudication import ProofOutcome, decide
from council.domain.config import ConfigError, parse
from council.domain.run_id import validate_run_id
from council.domain.sandbox import command
from council.domain.findings import State
from council.domain.merge import MergedFinding
from council.domain.verdict import Verdict


def merged() -> MergedFinding:
    return MergedFinding(
        dimension="correctness", file="a.py", line=2, severity="high",
        claims=("It is wrong.",), samples=(1,), proofs=(("present", {}),),
    )


def test_run_id_validation_is_a_pure_decision() -> None:
    assert validate_run_id("20261112-120000") == "20261112-120000"
    with pytest.raises(ValueError, match="one path segment"):
        validate_run_id("../escape")


def test_config_parse_reads_text_not_a_file(tmp_path: Path) -> None:
    """The parser cannot tell whether a path exists; that is the adapter's job."""
    config = parse('[proofs]\nallow = ["rg"]\ntimeout = 5\n')
    assert config.allow == frozenset({"rg"})
    assert config.timeout == 5
    assert not (tmp_path / "council.toml").exists()


def test_config_parse_names_the_text_in_an_error() -> None:
    with pytest.raises(ConfigError, match="bad.toml is not valid TOML"):
        parse("[proofs\n", name="bad.toml")


def test_adjudication_is_reproducible_from_outcomes() -> None:
    adj = decide([merged()], [[ProofOutcome(State.PROVEN, "the line exists")]])
    assert adj.findings[0].state is State.PROVEN
    assert adj.findings[0].detail == "the line exists"


def test_adjudication_refuses_a_mismatched_outcome_group() -> None:
    """A caller bug is refused, not silently zipped against the wrong finding."""
    with pytest.raises(ValueError, match="one outcome group per finding"):
        decide([merged()], [])


def test_a_missing_sample_is_in_the_pure_verdict() -> None:
    from council.domain.adjudication import verdict

    result = verdict(decide([], [], failed_samples=[2]))
    assert result.verdict is Verdict.INCOMPLETE
    assert "2" in result.reason


def test_sandbox_command_is_built_from_resolved_inputs() -> None:
    argv = command(["true"], Path("/tmp/repo"), bwrap="/bin/bwrap", path="/bin")
    assert argv[0] == "/bin/bwrap"
    assert argv[-1] == "true"
    assert "--setenv" in argv
    assert argv[argv.index("PATH") + 1] == "/bin"
    assert "--dir" in argv


def test_sandbox_command_outside_tmp_has_no_mountpoint() -> None:
    argv = command(["true"], Path("/srv/repo"), bwrap="/bin/bwrap")
    assert "--dir" not in argv
    assert argv[-1] == "true"


def test_sandbox_command_masks_user_homes() -> None:
    argv = command(["true"], Path("/srv/repo"), bwrap="/bin/bwrap")
    assert argv[argv.index("/home") - 1] == "--tmpfs"
    assert argv[argv.index("/root") - 1] == "--tmpfs"


def test_sandbox_command_masks_only_what_the_caller_names() -> None:
    argv = command(["true"], Path("/srv/repo"), bwrap="/bin/bwrap", masked=("/home",))
    assert argv[argv.index("/home") - 1] == "--tmpfs"
    assert "--tmpfs" not in argv[argv.index("/root") - 1:] if "/root" in argv else True


def test_sandbox_command_binds_a_repo_under_home() -> None:
    argv = command(["true"], Path("/home/alice/repo"), bwrap="/bin/bwrap")
    index = argv.index("--dir")
    assert argv[index + 1] == "/home/alice"
    assert argv[index + 2:index + 5] == [
        "--ro-bind", "/home/alice/repo", "/home/alice/repo"]
