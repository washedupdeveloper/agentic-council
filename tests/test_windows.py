"""A file too large for one prompt: refused by default, windowed when asked.

An added file arrives as one hunk carrying every line, so a file past the budget
has no smaller boundary to fall back on. These tests hold both halves of the
answer: the refusal states what splitting would cost, and the opt-in split
produces units that each fit and tile the file.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from council.cli import _request
from council.cli_parser import build_parser
from council.repo import ReviewError
from council.run import PromptTooLarge, ReviewRequest, plan, review
from council.schema import DIMENSIONS
from council.verdict import Verdict

PROMPT = "Base {{base}}\n\n{{diff}}\n"
LINES = 300
BUDGET = 512


def git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=repo, check=True,
                          capture_output=True, text=True).stdout.strip()


def big_repo(tmp_path: Path) -> tuple[Path, Path]:
    """A repository whose new file is 300 lines: one hunk, far past the budget."""
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q")
    git(repo, "config", "user.email", "test@example.invalid")
    git(repo, "config", "user.name", "test")
    (repo / "base.py").write_text("# base\n", encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "base")
    (repo / "big.py").write_text(
        "".join(f"v{index} = {index}\n" for index in range(LINES)), encoding="utf-8")
    prompt = tmp_path / "prompt.md"
    prompt.write_text(PROMPT, encoding="utf-8")
    return repo, prompt


def body() -> str:
    sections: dict[str, list[dict[str, Any]]] = {name: [] for name in DIMENSIONS}
    return json.dumps({"sections": sections})


def wanted(repo: Path, prompt: Path, run_id: str, **overrides: Any) -> ReviewRequest:
    options: dict[str, Any] = {"repo": repo, "base": "HEAD", "samples": 1,
                               "run_id": run_id, "prompt": prompt,
                               "max_prompt_bytes": BUDGET}
    options.update(overrides)
    return ReviewRequest(**options)


def test_a_file_too_large_for_one_prompt_states_its_window_cost(tmp_path: Path) -> None:
    repo, prompt = big_repo(tmp_path)
    with pytest.raises(PromptTooLarge) as raised:
        review(wanted(repo, prompt, "refused"), lambda _: body())
    message = str(raised.value)
    assert "windows" in message
    assert "--window-large-files" in message
    assert raised.value.windows is not None and raised.value.windows > 1


def test_windowing_splits_a_file_into_units_that_fit(tmp_path: Path) -> None:
    repo, prompt = big_repo(tmp_path)
    report = review(wanted(repo, prompt, "windowed", window_large_files=True),
                    lambda _: body())

    payload = json.loads((report.run_dir / "verdict.json").read_text(encoding="utf-8"))
    units = payload["units"]
    assert len(units) > 1
    assert all(unit["window"] is True for unit in units)
    assert all(unit["prompt_bytes"] <= BUDGET for unit in units)

    spans = [(unit["ranges"][0]["start"], unit["ranges"][0]["end"]) for unit in units]
    assert spans == sorted(spans)
    covered = [line for start, end in spans for line in range(start, end + 1)]
    assert covered == list(range(1, LINES + 1))


def test_windowing_past_the_window_limit_is_refused(tmp_path: Path) -> None:
    repo, prompt = big_repo(tmp_path)
    with pytest.raises(ReviewError, match="--max-windows"):
        review(wanted(repo, prompt, "too-many", window_large_files=True, max_windows=2),
               lambda _: body())


def test_a_finding_inside_a_window_fails_the_run(tmp_path: Path) -> None:
    repo, prompt = big_repo(tmp_path)
    line = 150

    def runner(_: str) -> str:
        sections: dict[str, list[dict[str, Any]]] = {name: [] for name in DIMENSIONS}
        sections["correctness"] = [{
            "severity": "high", "file": "big.py", "line": line, "claim": "It is wrong.",
            "proof": {"kind": "present",
                      "params": {"path": "big.py", "line": line,
                                 "text": f"v{line - 1} = {line - 1}"}},
        }]
        return json.dumps({"sections": sections})

    report = review(wanted(repo, prompt, "window-fail", window_large_files=True), runner)
    assert report.verdict is Verdict.FAIL


def test_the_plan_states_the_windows_and_their_samples(tmp_path: Path) -> None:
    repo, prompt = big_repo(tmp_path)
    planned = plan(wanted(repo, prompt, "planned", window_large_files=True, samples=None))
    assert planned.windows == len(planned.units) > 1
    assert planned.estimated_samples == (len(planned.units), len(planned.units) * 3)


def test_the_cli_passes_the_window_flags_into_the_request() -> None:
    args = build_parser().parse_args(["review", "--window-large-files", "--max-windows", "7"])
    built = _request(args)
    assert built.window_large_files is True
    assert built.max_windows == 7


def test_the_window_flags_are_off_by_default() -> None:
    args = build_parser().parse_args(["review"])
    built = _request(args)
    assert built.window_large_files is False
    assert built.max_windows == 200
