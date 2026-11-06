"""The base revision: every fallback is tested, because a wrong base looks healthy.

A review of the wrong range produces findings and a verdict like any other; the
only trace is the number on the left of the diff. So each step of the chain gets
a repository shaped to reach it, and the refusal gets one too.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from council.base import BaseError, resolve_base


def git(repo: Path, *args: str) -> str:
    proc = subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)
    return proc.stdout.strip()


def make_repo(tmp_path: Path, commits: int) -> tuple[Path, list[str]]:
    git(tmp_path, "init", "-q")
    git(tmp_path, "config", "user.email", "test@example.invalid")
    git(tmp_path, "config", "user.name", "test")
    shas: list[str] = []
    for index in range(commits):
        (tmp_path / "f.txt").write_text(f"{index}\n", encoding="utf-8")
        git(tmp_path, "add", "f.txt")
        git(tmp_path, "commit", "-qm", f"commit {index}")
        shas.append(git(tmp_path, "rev-parse", "HEAD"))
    return tmp_path, shas


def test_without_an_origin_it_falls_back_to_head_tilde_one(tmp_path: Path) -> None:
    repo, shas = make_repo(tmp_path, 2)
    assert resolve_base(repo) == shas[0]


def test_origin_head_wins_and_uses_the_merge_base(tmp_path: Path) -> None:
    """origin/HEAD three commits back: the base is the fork point, not the tip."""
    repo, shas = make_repo(tmp_path, 3)
    git(repo, "update-ref", "refs/remotes/origin/HEAD", shas[0])
    assert resolve_base(repo) == shas[0]


def test_the_merge_base_is_taken_not_the_tip(tmp_path: Path) -> None:
    repo, shas = make_repo(tmp_path, 3)
    git(repo, "update-ref", "refs/remotes/origin/HEAD", shas[1])
    assert resolve_base(repo) == shas[1]


def test_one_commit_and_no_origin_refuses(tmp_path: Path) -> None:
    repo, _ = make_repo(tmp_path, 1)
    with pytest.raises(BaseError, match="no base revision"):
        resolve_base(repo)


def test_an_explicit_base_is_resolved_to_a_commit(tmp_path: Path) -> None:
    repo, shas = make_repo(tmp_path, 2)
    assert resolve_base(repo, "HEAD") == shas[1]
    assert resolve_base(repo, "HEAD~1") == shas[0]


def test_an_explicit_base_that_does_not_exist_is_an_error_not_a_fallback(tmp_path: Path) -> None:
    repo, _ = make_repo(tmp_path, 2)
    with pytest.raises(BaseError, match="--base"):
        resolve_base(repo, "does-not-exist")