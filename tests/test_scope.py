"""Scope is a pure decision; staged review is a distinct diff source."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from council.domain.scope import Scope, ScopeError
from council.repo import diff
from council.run import ReviewError, ReviewRequest, review
from council.schema import DIMENSIONS

PATCH = (
    "diff --git a/src/a.py b/src/a.py\n"
    "--- a/src/a.py\n"
    "+++ b/src/a.py\n"
    "@@ -1 +1 @@\n"
    "-old\n"
    "+new\n"
    "diff --git a/docs/b.md b/docs/b.md\n"
    "--- a/docs/b.md\n"
    "+++ b/docs/b.md\n"
    "@@ -1 +1 @@\n"
    "-old\n"
    "+new\n"
)


def _body() -> str:
    return json.dumps({"sections": {name: [] for name in DIMENSIONS}})


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=repo, check=True,
                          capture_output=True, text=True).stdout.strip()


def _repo(tmp_path: Path) -> tuple[Path, str]:
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "test@example.invalid")
    _git(tmp_path, "config", "user.name", "test")
    (tmp_path / "base.txt").write_text("base\n", encoding="utf-8")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-qm", "base")
    return tmp_path, _git(tmp_path, "rev-parse", "HEAD")


def test_includes_are_callers_and_empty_includes_everything() -> None:
    scope = Scope.create(("src/**", "tests/*.py"))
    assert scope.keeps("src/a.py")
    assert scope.keeps("src/deep/a.py")
    assert scope.keeps("tests/test_a.py")
    assert not scope.keeps("docs/a.md")
    assert Scope.create().keeps("anything/at/all")


def test_star_stays_in_one_segment_and_double_star_recurses() -> None:
    scope = Scope.create(("src/*.py",))
    assert scope.keeps("src/a.py")
    assert not scope.keeps("src/deep/a.py")
    recursive = Scope.create(("src/**/*.py",))
    assert recursive.keeps("src/a.py")
    assert recursive.keeps("src/deep/a.py")
    assert not recursive.keeps("src/deep/a.txt")


def test_exclude_wins() -> None:
    scope = Scope.create(("**/*.py",), ("src/generated/**",))
    assert scope.keeps("src/a.py")
    assert not scope.keeps("src/generated/a.py")
    assert "excluded" in scope.decide("src/generated/a.py").reason


@pytest.mark.parametrize("pattern", ["", " /absolute", ".", "../up", "a//b",
                                     "a\\b", "\x00bad"])
def test_a_bad_scope_pattern_is_refused(pattern: str) -> None:
    with pytest.raises(ScopeError):
        Scope.create((pattern,))


def test_an_absolute_scope_pattern_is_refused() -> None:
    with pytest.raises(ScopeError):
        Scope.create(("/absolute",))


def test_filter_names_every_dropped_path() -> None:
    text, ignored = Scope.create(("src/**",)).filter_patch(PATCH)
    assert "src/a.py" in text
    assert "docs/b.md" not in text
    assert [(item.path, item.reason, item.pattern) for item in ignored] == [
        ("docs/b.md", "outside include", None),
    ]


def test_filter_excluded_path_names_the_pattern() -> None:
    text, ignored = Scope.create((), ("docs/**",)).filter_patch(PATCH)
    assert "src/a.py" in text
    assert "docs/b.md" not in text
    assert ignored[0].pattern == "docs/**"


def test_staged_diff_reads_only_the_index(tmp_path: Path) -> None:
    repo, base = _repo(tmp_path)
    (tmp_path / "staged.py").write_text("staged\n", encoding="utf-8")
    _git(repo, "add", "staged.py")
    (tmp_path / "unstaged.py").write_text("unstaged\n", encoding="utf-8")

    staged = diff(repo, base, staged=True)
    assert "staged.py" in staged.patch
    assert "unstaged.py" not in staged.patch
    assert staged.skipped == ()

    worktree = diff(repo, base)
    assert "staged.py" in worktree.patch
    assert "unstaged.py" in worktree.patch


def test_a_review_can_be_scoped_and_names_what_it_dropped(tmp_path: Path) -> None:
    repo, base = _repo(tmp_path)
    (repo / "src").mkdir()
    (repo / "docs").mkdir()
    (repo / "src" / "a.py").write_text("print('new')\n", encoding="utf-8")
    (repo / "docs" / "b.md").write_text("new docs\n", encoding="utf-8")
    seen: list[str] = []

    def runner(prompt: str) -> str:
        seen.append(prompt)
        return _body()

    request = ReviewRequest(repo=repo, base=base, samples=1, run_id="scope",
                            state_dir=tmp_path / "state",
                            include=("src/**",))
    report = review(request, runner)
    payload = json.loads((report.run_dir / "verdict.json").read_text(encoding="utf-8"))

    assert "src/a.py" in seen[0]
    assert "docs/b.md" not in seen[0]
    assert payload["scope_ignored"] == [
        {"path": "docs/b.md", "reason": "outside include", "pattern": None},
    ]
    assert payload["scope"] == {"include": ["src/**"], "exclude": []}
    assert report.scope_ignored[0].path == "docs/b.md"


def test_a_scope_that_removes_everything_is_a_start_failure(tmp_path: Path) -> None:
    repo, base = _repo(tmp_path)
    (repo / "a.py").write_text("new\n", encoding="utf-8")
    calls: list[str] = []

    def runner(prompt: str) -> str:
        calls.append(prompt)
        return _body()

    with pytest.raises(ReviewError, match="no reviewable text in scope"):
        review(ReviewRequest(repo=repo, base=base, run_id="empty-scope",
                             state_dir=tmp_path / "state",
                             include=("nothing/**",)), runner)
    assert calls == []
    assert not (tmp_path / "state" / "empty-scope").exists()


def test_staged_review_records_the_index_source(tmp_path: Path) -> None:
    repo, base = _repo(tmp_path)
    (repo / "staged.py").write_text("staged\n", encoding="utf-8")
    _git(repo, "add", "staged.py")
    (repo / "unstaged.py").write_text("unstaged\n", encoding="utf-8")
    seen: list[str] = []

    def runner(prompt: str) -> str:
        seen.append(prompt)
        return _body()

    report = review(ReviewRequest(repo=repo, base=base, samples=1, run_id="staged",
                                  state_dir=tmp_path / "state", staged=True), runner)
    payload = json.loads((report.run_dir / "verdict.json").read_text(encoding="utf-8"))
    assert payload["staged"] is True
    assert payload["worktree"] is False
    assert "staged.py" in seen[0]
    assert "unstaged.py" not in seen[0]


def test_a_scope_pattern_error_reaches_the_request_as_a_start_failure(tmp_path: Path) -> None:
    repo, base = _repo(tmp_path)
    with pytest.raises(ReviewError, match="must be repository-relative"):
        review(ReviewRequest(repo=repo, base=base, run_id="bad-scope",
                             state_dir=tmp_path / "state",
                             include=("/absolute",)), lambda _: _body())


def test_excluding_the_baseline_does_not_hide_its_edit(tmp_path: Path) -> None:
    repo, _ = _repo(tmp_path)
    baseline = repo / "baseline.json"
    baseline.write_text('{"version": 1, "entries": []}\n', encoding="utf-8")
    _git(repo, "add", "baseline.json")
    _git(repo, "commit", "-qm", "baseline")
    base = _git(repo, "rev-parse", "HEAD")
    baseline.write_text('{"version": 1, "entries": []}\n# edited\n', encoding="utf-8")
    (repo / "a.py").write_text("new\n", encoding="utf-8")

    with pytest.raises(ReviewError, match="baseline file is changed"):
        review(ReviewRequest(repo=repo, base=base, run_id="scope-baseline",
                             state_dir=tmp_path / "state",
                             baseline=Path("baseline.json"),
                             baseline_from_base=True,
                             include=("a.py",)), lambda _: _body())
