"""`council pr`: resolve the pull request, verify the checkout, never switch it."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from council import pr as pr_module
from council.pr import PullRequest, resolve, verify_checkout
from council.repo import ReviewError

BASE = "a" * 40
HEAD = "b" * 40
DATA = {
    "number": 7,
    "url": "https://github.com/o/r/pull/7",
    "title": "A change",
    "baseRefOid": BASE,
    "headRefOid": HEAD,
    "baseRefName": "main",
    "headRefName": "topic",
}


def pull() -> PullRequest:
    return PullRequest(7, DATA["url"], DATA["title"], BASE, HEAD, "main", "topic")


def test_resolve_reads_the_pull_request(tmp_path: Path,
                                        monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pr_module.shutil, "which", lambda name: "/usr/bin/gh")
    seen: dict[str, object] = {}

    def run(argv: list[str], **kwargs: object) -> SimpleNamespace:
        seen["argv"] = argv
        seen["cwd"] = kwargs["cwd"]
        return SimpleNamespace(returncode=0, stdout=json.dumps(DATA), stderr="")

    monkeypatch.setattr(pr_module.subprocess, "run", run)
    result = resolve(7, tmp_path)
    assert result == pull()
    assert seen["argv"] == ["/usr/bin/gh", "pr", "view", "7", "--json",
                            pr_module.FIELDS]
    assert seen["cwd"] == tmp_path


def test_missing_gh_is_a_review_error(monkeypatch: pytest.MonkeyPatch,
                                      tmp_path: Path) -> None:
    monkeypatch.setattr(pr_module.shutil, "which", lambda name: None)
    with pytest.raises(ReviewError, match="GitHub CLI"):
        resolve(7, tmp_path)


def test_gh_failure_is_reported(monkeypatch: pytest.MonkeyPatch,
                                tmp_path: Path) -> None:
    monkeypatch.setattr(pr_module.shutil, "which", lambda name: "/usr/bin/gh")
    monkeypatch.setattr(pr_module.subprocess, "run",
                        lambda *a, **k: SimpleNamespace(returncode=1, stdout="",
                                                        stderr="no pull requests found"))
    with pytest.raises(ReviewError, match="no pull requests found"):
        resolve(7, tmp_path)


def test_an_incomplete_answer_is_refused(monkeypatch: pytest.MonkeyPatch,
                                         tmp_path: Path) -> None:
    monkeypatch.setattr(pr_module.shutil, "which", lambda name: "/usr/bin/gh")
    monkeypatch.setattr(pr_module.subprocess, "run",
                        lambda *a, **k: SimpleNamespace(returncode=0, stdout='{"number": 7}',
                                                        stderr=""))
    with pytest.raises(ReviewError, match="incomplete"):
        resolve(7, tmp_path)


def test_a_checkout_at_another_commit_is_refused(monkeypatch: pytest.MonkeyPatch,
                                                 tmp_path: Path) -> None:
    monkeypatch.setattr(pr_module, "output",
                        lambda repo, *args: "c" * 40 if args[0] == "rev-parse" else "")
    with pytest.raises(ReviewError, match="gh pr checkout 7"):
        verify_checkout(pull(), tmp_path)


def test_a_dirty_worktree_is_refused(monkeypatch: pytest.MonkeyPatch,
                                     tmp_path: Path) -> None:
    monkeypatch.setattr(pr_module, "output",
                        lambda repo, *args: HEAD if args[0] == "rev-parse" else " M f.py\n")
    with pytest.raises(ReviewError, match="local changes"):
        verify_checkout(pull(), tmp_path)


def test_a_clean_checkout_at_the_head_is_accepted(monkeypatch: pytest.MonkeyPatch,
                                                  tmp_path: Path) -> None:
    monkeypatch.setattr(pr_module, "output",
                        lambda repo, *args: HEAD if args[0] == "rev-parse" else "")
    verify_checkout(pull(), tmp_path)


def test_a_gh_that_cannot_run_is_a_review_error(monkeypatch: pytest.MonkeyPatch,
                                                tmp_path: Path) -> None:
    monkeypatch.setattr(pr_module.shutil, "which", lambda name: "/usr/bin/gh")
    monkeypatch.setattr(pr_module.subprocess, "run",
                        lambda *a, **k: (_ for _ in ()).throw(OSError("no such cwd")))
    with pytest.raises(ReviewError, match="could not run"):
        resolve(7, tmp_path)


def test_a_gh_timeout_is_a_review_error(monkeypatch: pytest.MonkeyPatch,
                                        tmp_path: Path) -> None:
    monkeypatch.setattr(pr_module.shutil, "which", lambda name: "/usr/bin/gh")

    def timeout(*args: object, **kwargs: object) -> object:
        raise pr_module.subprocess.TimeoutExpired(["gh"], 30)

    monkeypatch.setattr(pr_module.subprocess, "run", timeout)
    with pytest.raises(ReviewError, match="could not run"):
        resolve(7, tmp_path)


def test_a_non_positive_pull_request_is_refused(monkeypatch: pytest.MonkeyPatch,
                                                tmp_path: Path) -> None:
    monkeypatch.setattr(pr_module.shutil, "which", lambda name: "/usr/bin/gh")
    for number in (0, -1):
        with pytest.raises(ReviewError, match="positive integer"):
            resolve(number, tmp_path)
