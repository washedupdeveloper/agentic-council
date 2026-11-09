"""The Hermes runner: the argv it builds, and how a failure is reported."""

from __future__ import annotations

from pathlib import Path

import pytest

from council.runner import hermes_runner


def script(tmp_path: Path, body: str, code: int = 0) -> Path:
    path = tmp_path / "hermes"
    path.write_text(f"#!/bin/sh\n{body}\nexit {code}\n", encoding="utf-8", newline="\n")
    path.chmod(0o755)
    return path


def test_the_prompt_is_passed_as_a_file_and_the_profile_as_a_flag(tmp_path: Path) -> None:
    binary = script(tmp_path, 'printf "%s" "$*"')
    output = hermes_runner("council-generalist", binary=str(binary), timeout=10)("hello")
    assert "-p council-generalist" in output
    assert "--query-file" in output
    assert "--oneshot" in output


def test_the_answer_is_returned_unchanged(tmp_path: Path) -> None:
    binary = script(tmp_path, 'printf \'{"sections": {}}\'')
    assert hermes_runner("p", binary=str(binary), timeout=10)("q") == '{"sections": {}}'


def test_a_nonzero_exit_is_an_oserror_so_the_sample_retries(tmp_path: Path) -> None:
    binary = script(tmp_path, 'printf "provider refused" >&2', code=1)
    with pytest.raises(OSError, match="exited 1"):
        hermes_runner("p", binary=str(binary), timeout=10)("q")


def test_a_missing_binary_is_an_oserror(tmp_path: Path) -> None:
    with pytest.raises(OSError, match="not installed"):
        hermes_runner("p", binary=str(tmp_path / "absent"), timeout=10)("q")


def test_the_prompt_is_written_verbatim(tmp_path: Path) -> None:
    binary = script(tmp_path, 'cat "$5"')
    prompt = 'a "quoted" $(subshell) `backtick`\nline two\n'
    assert hermes_runner("p", binary=str(binary), timeout=10)(prompt) == prompt
