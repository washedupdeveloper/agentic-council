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