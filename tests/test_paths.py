"""Runs live inside the checkout, at a path a caller cannot escape."""

from __future__ import annotations

from pathlib import Path

import pytest

from council.paths import run_dir, runs_root


def test_runs_are_inside_the_repository(tmp_path: Path) -> None:
    assert runs_root(tmp_path) == tmp_path / ".council" / "runs"


def test_a_run_id_is_one_segment(tmp_path: Path) -> None:
    assert run_dir(tmp_path, "20261106-120000") == tmp_path / ".council" / "runs" / "20261106-120000"


@pytest.mark.parametrize("run_id", ["", ".", "..", "a/b", "a\\b"])
def test_a_run_id_cannot_escape(tmp_path: Path, run_id: str) -> None:
    with pytest.raises(ValueError, match="run id"):
        run_dir(tmp_path, run_id)


@pytest.mark.parametrize("run_id", ["a\nb", "a\0b", "a:b", "a?b", "a*b", "a|b",
                                    "a<b", "a>b", 'a"b', "x" * 129])
def test_a_run_id_must_be_a_portable_segment(tmp_path: Path, run_id: str) -> None:
    with pytest.raises(ValueError, match="run id"):
        run_dir(tmp_path, run_id)


def test_a_state_file_is_refused(tmp_path: Path) -> None:
    (tmp_path / ".council").write_text("not a directory", encoding="utf-8")
    with pytest.raises(ValueError, match="not a directory"):
        run_dir(tmp_path, "r1")


def test_a_runs_file_is_refused(tmp_path: Path) -> None:
    (tmp_path / ".council").mkdir()
    (tmp_path / ".council" / "runs").write_text("not a directory", encoding="utf-8")
    with pytest.raises(ValueError, match="not a directory"):
        run_dir(tmp_path, "r1")


def test_a_symlinked_state_directory_is_refused(tmp_path: Path) -> None:
    """A pre-existing `.council -> elsewhere` must not move the writes out."""
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (tmp_path / "repo").mkdir()
    (tmp_path / "repo" / ".council").symlink_to(elsewhere)
    with pytest.raises(ValueError, match="symlink"):
        run_dir(tmp_path / "repo", "r1")


def test_a_symlinked_runs_directory_is_refused(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / ".council").mkdir(parents=True)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (repo / ".council" / "runs").symlink_to(elsewhere)
    with pytest.raises(ValueError, match="symlink"):
        run_dir(repo, "r1")
