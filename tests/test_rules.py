"""Rules: the repository's own documents reach the prompt, once, and are recorded.

dsh's review skill states the rule this feature implements: "Read the
requirements before judging the diff... Judging a diff against memory of the
rules is how a violation passes review." council had caller-supplied references
and nothing that tied a repository's documents to the paths they govern.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from council.config import ConfigError
from council.repo import ReviewError
from council.run import ReviewRequest, plan, review
from council.domain.schema import DIMENSIONS

SENTINEL = "never log the api key"


def git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=repo, check=True,
                          capture_output=True, text=True).stdout.strip()


def make_repo(tmp_path: Path, rules: str, doc: str | None = None) -> Path:
    git(tmp_path, "init", "-q")
    git(tmp_path, "config", "user.email", "test@example.invalid")
    git(tmp_path, "config", "user.name", "test")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "rule.md").write_text(
        doc if doc is not None else f"# House rules\n\n{SENTINEL}.\n", encoding="utf-8")
    (tmp_path / "f0.py").write_text("# base\n", encoding="utf-8")
    (tmp_path / "council.toml").write_text(rules, encoding="utf-8")
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-qm", "base")
    (tmp_path / "f1.py").write_text("# second\n", encoding="utf-8")
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-qm", "second")
    (tmp_path / "a.py").write_text("one\ntwo\n", encoding="utf-8")
    return tmp_path


def body() -> str:
    sections: dict[str, list[dict[str, Any]]] = {name: [] for name in DIMENSIONS}
    return json.dumps({"sections": sections})


def prompts() -> tuple[list[str], Any]:
    seen: list[str] = []

    def runner(prompt: str) -> str:
        seen.append(prompt)
        return body()

    return seen, runner


RULE = '[[rules]]\nglob = "a.py"\ndoc = "docs/rule.md"\n'


def test_a_rule_document_reaches_the_prompt(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, RULE)
    seen, runner = prompts()
    report = review(ReviewRequest(repo=repo, samples=1, allow_single_sample=True, run_id="rules"), runner)

    assert SENTINEL in seen[0]
    assert "## Repository rules" in seen[0]
    assert "not instructions" in seen[0]
    payload = json.loads((report.run_dir / "verdict.json").read_text(encoding="utf-8"))
    assert payload["rules"] == [
        {"glob": "a.py", "doc": "docs/rule.md", "paths": ["a.py"], "truncated": False}]


def test_a_rule_that_matches_nothing_is_not_recorded(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, '[[rules]]\nglob = "other/**"\ndoc = "docs/rule.md"\n')
    seen, runner = prompts()
    report = review(ReviewRequest(repo=repo, samples=1, allow_single_sample=True, run_id="unused"), runner)

    assert SENTINEL not in seen[0]
    assert "## Repository rules" not in seen[0]
    payload = json.loads((report.run_dir / "verdict.json").read_text(encoding="utf-8"))
    assert payload["rules"] == []


def test_a_rule_document_that_cannot_be_read_is_a_start_failure(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, '[[rules]]\nglob = "a.py"\ndoc = "docs/gone.md"\n')
    seen, runner = prompts()
    with pytest.raises(ReviewError, match="docs/gone.md"):
        review(ReviewRequest(repo=repo, samples=1, allow_single_sample=True, run_id="missing"), runner)
    assert seen == []


def test_a_large_rule_document_is_capped_and_marked(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, RULE, doc="zq" * 12500)
    seen, runner = prompts()
    report = review(ReviewRequest(repo=repo, samples=1, allow_single_sample=True, run_id="capped"), runner)

    assert "truncated at 20000 bytes" in seen[0]
    # The document, not the whole prompt, is what the cap bounds: 20,000 bytes
    # is 10,000 "zq" pairs, and the sixteenth pair of the original is gone.
    assert seen[0].count("zq") == 10000
    payload = json.loads((report.run_dir / "verdict.json").read_text(encoding="utf-8"))
    assert payload["rules"][0]["truncated"] is True


def test_two_rules_naming_one_document_read_it_once(tmp_path: Path) -> None:
    rules = ('[[rules]]\nglob = "a.py"\ndoc = "docs/rule.md"\n'
             '[[rules]]\nglob = "*.py"\ndoc = "docs/rule.md"\n')
    repo = make_repo(tmp_path, rules)
    seen, runner = prompts()
    report = review(ReviewRequest(repo=repo, samples=1, allow_single_sample=True, run_id="twice"), runner)

    assert seen[0].count(SENTINEL) == 1
    payload = json.loads((report.run_dir / "verdict.json").read_text(encoding="utf-8"))
    assert len(payload["rules"]) == 2


def test_a_rule_document_is_counted_in_every_window(tmp_path: Path) -> None:
    """A window sized without the rules block is a window that does not fit."""
    repo = make_repo(tmp_path, RULE, doc="rule " * 300)
    (repo / "a.py").write_text("".join(f"line {index} = {index}\n" for index in range(200)),
                               encoding="utf-8")
    seen, runner = prompts()
    report = review(ReviewRequest(repo=repo, samples=1, allow_single_sample=True, run_id="windowed-rules",
                                  max_prompt_bytes=6000, window_large_files=True), runner)
    payload = json.loads((report.run_dir / "verdict.json").read_text(encoding="utf-8"))
    assert payload["verdict"] == "pass"
    assert payload["units"]
    assert all(unit["prompt_bytes"] <= 6000 for unit in payload["units"])
    assert payload["rules"][0]["doc"] == "docs/rule.md"


def test_the_plan_names_the_rules_a_review_would_use(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, RULE)
    planned = plan(ReviewRequest(repo=repo, samples=1, allow_single_sample=True, run_id="planned"))
    assert [hit.doc for hit in planned.rules] == ["docs/rule.md"]
    assert planned.rules[0].paths == ("a.py",)


@pytest.mark.parametrize("text, message", [
    ('[[rules]]\nglob = "a.py"\n', "needs a non-empty doc"),
    ('[[rules]]\nglob = "../a.py"\ndoc = "docs/rule.md"\n', "repository-relative"),
    ('[[rules]]\nglob = "/etc/passwd"\ndoc = "docs/rule.md"\n', "repository-relative"),
    ('[[rules]]\nglob = "a.py"\ndoc = "docs/rule.md"\nkind = "review"\n', "unknown key"),
    ('rules = "docs/rule.md"\n', "array of tables"),
])
def test_the_configuration_refuses_a_rule_it_cannot_honour(text: str, message: str) -> None:
    from council.domain.config import parse

    with pytest.raises(ConfigError, match=message):
        parse(text)
