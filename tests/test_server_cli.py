"""The thin subprocess boundary is tested against the real council CLI."""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from council_server.cli import (
    CouncilError,
    ReviewOptions,
    ServerConfig,
    _append_review_args,
    local_path,
    run_plan,
    run_review,
)

import council_server

SOURCE = Path(council_server.__file__).resolve().parent.parent


def config(repo: Path, tmp_path: Path, reviewer: Path | None = None) -> ServerConfig:
    return ServerConfig(root=repo, state_root=tmp_path / "state",
                        reviewer=str(reviewer) if reviewer else None,
                        profile="test", no_sandbox=True,
                        command=(sys.executable, "-m", "council"))


def test_plan_is_the_public_cli_plan(review_repo: Path, tmp_path: Path,
                                     child_env: dict[str, str]) -> None:
    result = asyncio.run(run_plan(config(review_repo, tmp_path),
                                  ReviewOptions(repo=".", base="HEAD~1")))
    assert isinstance(result.payload, dict)
    assert result.payload["base"]
    assert result.payload["head"]
    assert isinstance(result.payload["units"], list)


def test_review_runs_the_core_and_retains_evidence(
        review_repo: Path, tmp_path: Path, fake_reviewer: Path) -> None:
    result = asyncio.run(run_review(
        config(review_repo, tmp_path, fake_reviewer),
        ReviewOptions(repo=".", base="HEAD~1")))
    assert isinstance(result.payload, dict)
    assert result.payload["verdict"] == "fail"
    assert result.returncode == 1
    assert result.run_dir is not None
    assert (result.run_dir / "verdict.json").is_file()
    assert (result.run_dir / "sample-1.json").is_file()


def test_a_repository_outside_the_root_is_refused(
        review_repo: Path, tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    with pytest.raises(CouncilError, match="outside the server root"):
        asyncio.run(run_plan(config(review_repo, tmp_path),
                             ReviewOptions(repo=str(outside))))


def test_the_same_plan_as_the_cli(review_repo: Path, tmp_path: Path,
                                  child_env: dict[str, str]) -> None:
    result = asyncio.run(run_plan(config(review_repo, tmp_path),
                                  ReviewOptions(repo=".", base="HEAD~1")))
    cli = subprocess.run(
        [sys.executable, "-m", "council", "review", "--plan", "--json",
         "-C", str(review_repo), "--base", "HEAD~1"],
        cwd=review_repo, env=child_env, capture_output=True, text=True, check=False)
    assert cli.returncode == 0, cli.stderr
    assert json.loads(cli.stdout) == result.payload


def test_missing_council_is_a_clean_error(tmp_path: Path) -> None:
    server = ServerConfig(root=tmp_path, state_root=tmp_path / "state",
                          command=("/definitely/not/council",))
    with pytest.raises(CouncilError, match="cannot start council"):
        asyncio.run(run_plan(server, ReviewOptions()))


@pytest.mark.skipif(os.name == "nt", reason="WSL path translation")
def test_a_windows_workspace_path_is_translated_for_wsl() -> None:
    assert local_path(r"C:\Users\you\repo") == Path("/mnt/c/Users/you/repo")


def test_a_posix_workspace_path_is_not_translated() -> None:
    assert local_path("/home/user/repo") == Path("/home/user/repo")


def test_the_server_passes_its_selected_agent(tmp_path: Path) -> None:
    server = ServerConfig(root=tmp_path, state_root=tmp_path / "state",
                          agent="example", profile="review", no_sandbox=True)
    argv: list[str] = []
    _append_review_args(server, ReviewOptions(), argv)
    assert ["--agent", "example"] == argv[argv.index("--agent"):argv.index("--agent") + 2]
    assert "--profile" in argv and "review" in argv
    assert "--reviewer" not in argv
