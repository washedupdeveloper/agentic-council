"""The Hermes runner: the argv it builds, and how a failure is reported."""

from __future__ import annotations

import sys
import shutil
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


def test_the_reasoning_level_is_passed_to_the_process(tmp_path: Path) -> None:
    binary = script(tmp_path, 'printf "%s" "$*"')
    output = hermes_runner("council-generalist", binary=str(binary), timeout=10,
                           reasoning="none")("hello")
    assert "--reasoning none" in output


def test_no_reasoning_flag_when_the_profile_decides(tmp_path: Path) -> None:
    binary = script(tmp_path, 'printf "%s" "$*"')
    output = hermes_runner("p", binary=str(binary), timeout=10)("hello")
    assert "--reasoning" not in output


def py_script(tmp_path: Path, body: str, code: int = 0) -> Path:
    path = tmp_path / "hermes"
    path.write_text(
        f"#!{sys.executable}\nimport json, sys, time\n{body}\nraise SystemExit({code})\n",
        encoding="utf-8", newline="\n")
    path.chmod(0o755)
    return path


def test_a_stream_returns_the_result_text(tmp_path: Path) -> None:
    binary = py_script(tmp_path, '''
print(json.dumps({"type": "text", "text": "{\\"sections\\": "}))
print(json.dumps({"type": "text", "text": "{}}"}))
print(json.dumps({"type": "result", "exit_code": 0, "text": "{\\"sections\\": {}}"}))
''')
    answer = hermes_runner("p", binary=str(binary), timeout=10, stream=True,
                           idle_timeout=5)("q")
    assert answer == '{"sections": {}}'


def test_a_stream_without_a_result_returns_its_text(tmp_path: Path) -> None:
    binary = py_script(tmp_path, '''
print(json.dumps({"type": "text", "text": "one "}))
print(json.dumps({"type": "text", "text": "two"}))
''')
    answer = hermes_runner("p", binary=str(binary), timeout=10, stream=True,
                           idle_timeout=5)("q")
    assert answer == "one two"


def test_a_silent_stream_is_killed_at_the_idle_timeout(tmp_path: Path) -> None:
    binary = py_script(tmp_path, '''
print(json.dumps({"type": "system", "subtype": "init"}))
sys.stdout.flush()
time.sleep(10)
''')
    with pytest.raises(OSError, match="silent for 1s"):
        hermes_runner("p", binary=str(binary), timeout=30, stream=True,
                      idle_timeout=1)("q")


def test_a_stream_whose_child_holds_the_pipe_is_still_killed(tmp_path: Path) -> None:
    """A wrapper's sleep inherits stdout; killing only the wrapper leaves it open."""
    path = tmp_path / "hermes"
    path.write_text("#!/bin/sh\nprintf '%s\\n' '{\"type\":\"system\"}'\nsleep 10\n",
                    encoding="utf-8", newline="\n")
    path.chmod(0o755)
    with pytest.raises(OSError, match="silent for 1s"):
        hermes_runner("p", binary=str(path), timeout=30, stream=True,
                      idle_timeout=1)("q")


def test_a_stream_that_ends_without_an_answer_is_an_error(tmp_path: Path) -> None:
    binary = py_script(tmp_path, '''
print(json.dumps({"type": "system", "subtype": "init"}))
''')
    with pytest.raises(OSError, match="without an answer"):
        hermes_runner("p", binary=str(binary), timeout=10, stream=True,
                      idle_timeout=5)("q")


def test_a_stream_result_with_a_nonzero_exit_is_an_error(tmp_path: Path) -> None:
    binary = py_script(tmp_path, '''
print(json.dumps({"type": "result", "exit_code": 3, "text": ""}))
''')
    with pytest.raises(OSError, match="exited 3"):
        hermes_runner("p", binary=str(binary), timeout=10, stream=True,
                      idle_timeout=5)("q")


def test_a_non_utf8_answer_is_replaced_not_a_crash(tmp_path: Path) -> None:
    binary = py_script(tmp_path, 'import sys; sys.stdout.buffer.write(b"\\xff")')
    answer = hermes_runner("p", binary=str(binary), timeout=10)("q")
    assert "\ufffd" in answer


def test_a_non_utf8_stream_line_is_ignored_not_a_crash(tmp_path: Path) -> None:
    binary = py_script(tmp_path, 'import sys; sys.stdout.buffer.write(b"\\xff\\n")')
    with pytest.raises(OSError, match="without an answer"):
        hermes_runner("p", binary=str(binary), timeout=10, stream=True,
                      idle_timeout=5)("q")


def test_a_stream_result_with_empty_text_falls_back_to_text_events(tmp_path: Path) -> None:
    binary = py_script(tmp_path, '''
print(json.dumps({"type": "text", "text": "ok"}))
print(json.dumps({"type": "result", "exit_code": 0, "text": ""}))
''')
    answer = hermes_runner("p", binary=str(binary), timeout=10, stream=True,
                           idle_timeout=5)("q")
    assert answer == "ok"


def test_a_sandboxed_reviewer_cannot_write_to_the_host(tmp_path: Path) -> None:
    if shutil.which("bwrap") is None:
        pytest.skip("bwrap is not available")
    marker_home = Path.home() / "council-sandbox-leak"
    marker_tmp = Path("/tmp/council-sandbox-leak")
    for marker in (marker_home, marker_tmp):
        marker.unlink(missing_ok=True)
    binary = py_script(tmp_path, '''
from pathlib import Path
Path.home().joinpath("council-sandbox-leak").write_text("x")
Path("/tmp/council-sandbox-leak").write_text("x")
print(json.dumps({"sections": {}}))
''')
    answer = hermes_runner("p", binary=str(binary), timeout=20, sandbox=True)("q")
    assert answer.strip() == '{"sections": {}}'
    assert not marker_home.exists()
    assert not marker_tmp.exists()


def test_a_symlinked_reviewer_runs_in_the_sandbox(tmp_path: Path) -> None:
    if shutil.which("bwrap") is None:
        pytest.skip("bwrap is not available")
    binary = py_script(tmp_path, 'print(json.dumps({"sections": {}}))')
    linked = tmp_path / "reviewer"
    linked.symlink_to(binary)
    answer = hermes_runner("p", binary=str(linked), timeout=20, sandbox=True)("q")
    assert answer.strip() == '{"sections": {}}'


def test_the_sandbox_needs_bwrap(tmp_path: Path,
                                 monkeypatch: pytest.MonkeyPatch) -> None:
    binary = py_script(tmp_path, 'print(json.dumps({"sections": {}}))')
    monkeypatch.setattr("council.runner.shutil.which", lambda name: None)
    with pytest.raises(OSError, match="bwrap is required"):
        hermes_runner("p", binary=str(binary), timeout=10, sandbox=True)("q")


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
