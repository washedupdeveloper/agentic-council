"""Git is read through one helper, so a fix is made in one place."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

from council.repo import ReviewError, git, init, output

SRC = Path(__file__).resolve().parent.parent / "src" / "council"
GIT_CALL = re.compile(r'subprocess\.run\(\s*\["git"')


def test_output_raises_when_git_fails(tmp_path: Path) -> None:
    with pytest.raises(ReviewError, match="rev-parse"):
        output(tmp_path, "rev-parse", "--verify", "does-not-exist")


def test_git_hands_back_a_failed_probe_instead_of_raising(tmp_path: Path) -> None:
    proc = git(tmp_path, "rev-parse", "--verify", "does-not-exist")
    assert proc.returncode != 0


def test_init_adds_the_state_directory_once(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    assert init(tmp_path) is True
    assert init(tmp_path) is False
    assert (tmp_path / ".gitignore").read_text(encoding="utf-8") == ".council/\n"


def test_git_is_called_in_one_module() -> None:
    """The same rule as `PROOF_KINDS == EXECUTORS`: one owner, checked both ways."""
    hits = sorted(
        path.name for path in SRC.glob("*.py")
        if GIT_CALL.search(path.read_text(encoding="utf-8"))
    )
    assert hits == ["repo.py"]