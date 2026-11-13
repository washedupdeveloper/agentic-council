"""Drive the real CLI through a stub reviewer: parser, request, prompt, verdict."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

import council.cli as cli


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=repo, check=True,
                          capture_output=True, text=True).stdout.strip()


def _repo(tmp_path: Path) -> tuple[Path, str]:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "test@example.invalid")
    _git(repo, "config", "user.name", "test")
    (repo / "base.txt").write_text("base\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "base")
    return repo, _git(repo, "rev-parse", "HEAD")


def _stub(tmp_path: Path, capture: Path) -> Path:
    binary = tmp_path / "hermes"
    binary.write_text(
        f"#!{sys.executable}\n"
        "import json, os, pathlib, sys\n"
        "args = sys.argv\n"
        "source = pathlib.Path(args[args.index('--query-file') + 1])\n"
        "pathlib.Path(os.environ['COUNCIL_CAPTURE']).write_text(\n"
        "    source.read_text(encoding='utf-8'), encoding='utf-8')\n"
        "names = ('security', 'performance', 'readability', 'correctness', 'architecture')\n"
        "print(json.dumps({'sections': {name: [] for name in names}}))\n",
        encoding="utf-8", newline="\n")
    binary.chmod(0o755)
    return binary


def _review(repo: Path, base: str, binary: Path, capture: Path,
            *extra: str, command: str = "review") -> tuple[str, dict[str, object]]:
    run_id = "scope-e2e"
    code = cli.main([
        command, "-C", str(repo), "--base", base, "--reviewer", str(binary),
        "--no-stream", "--no-sandbox", "--no-ephemeral", "--samples", "1",
        "--context-depth", "0", "--run-id", run_id, *extra,
    ])
    assert code == 0
    prompt = capture.read_text(encoding="utf-8")
    payload = json.loads(
        (repo / ".council" / "runs" / run_id / "verdict.json").read_text(encoding="utf-8"))
    return prompt, payload


def test_the_cli_scope_reaches_the_reviewer(tmp_path: Path,
                                            monkeypatch: pytest.MonkeyPatch) -> None:
    repo, base = _repo(tmp_path)
    (repo / "src").mkdir()
    (repo / "docs").mkdir()
    (repo / "src" / "a.py").write_text("print('new')\n", encoding="utf-8")
    (repo / "docs" / "b.md").write_text("exclude me\n", encoding="utf-8")
    (repo / "docs" / "keep.md").write_text("keep me\n", encoding="utf-8")
    capture = tmp_path / "prompt.txt"
    monkeypatch.setenv("COUNCIL_CAPTURE", str(capture))

    prompt, payload = _review(
        repo, base, _stub(tmp_path, capture), capture,
        "--include", "src/**", "--include", "docs/**", "--exclude", "docs/b.md")

    assert "src/a.py" in prompt
    assert "docs/keep.md" in prompt
    assert "docs/b.md" not in prompt
    assert payload["scope"] == {"include": ["src/**", "docs/**"],
                                "exclude": ["docs/b.md"]}
    assert payload["scope_ignored"] == [
        {"path": "docs/b.md", "reason": "excluded", "pattern": "docs/b.md"},
    ]


def test_the_cli_staged_mode_reaches_the_reviewer(tmp_path: Path,
                                                  monkeypatch: pytest.MonkeyPatch) -> None:
    repo, base = _repo(tmp_path)
    (repo / "staged.py").write_text("staged\n", encoding="utf-8")
    _git(repo, "add", "staged.py")
    (repo / "unstaged.py").write_text("unstaged\n", encoding="utf-8")
    capture = tmp_path / "prompt.txt"
    monkeypatch.setenv("COUNCIL_CAPTURE", str(capture))

    prompt, payload = _review(repo, base, _stub(tmp_path, capture), capture,
                              "--staged")

    assert "staged.py" in prompt
    assert "unstaged.py" not in prompt
    assert payload["staged"] is True
    assert payload["worktree"] is False


def test_ci_exposes_staged_mode() -> None:
    parser = cli.build_parser()
    assert parser.parse_args(["ci", "--staged"]).staged is True


def test_ci_runs_a_staged_review(tmp_path: Path,
                                 monkeypatch: pytest.MonkeyPatch) -> None:
    repo, base = _repo(tmp_path)
    (repo / "ci-staged.py").write_text("staged\n", encoding="utf-8")
    _git(repo, "add", "ci-staged.py")
    (repo / "ci-unstaged.py").write_text("unstaged\n", encoding="utf-8")
    capture = tmp_path / "prompt.txt"
    monkeypatch.setenv("COUNCIL_CAPTURE", str(capture))

    prompt, payload = _review(repo, base, _stub(tmp_path, capture), capture,
                              "--staged", command="ci")

    assert "ci-staged.py" in prompt
    assert "ci-unstaged.py" not in prompt
    assert payload["staged"] is True
    assert payload["worktree"] is False
