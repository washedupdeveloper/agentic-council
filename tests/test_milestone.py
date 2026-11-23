"""The milestone runner: evidence, predicates and the approval boundary."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOOL = ROOT / "tools" / "milestone.py"

FAKE = """#!/usr/bin/env python3
import os
import re
import subprocess
import sys
from pathlib import Path

args = sys.argv[1:]
query = Path(args[args.index("--query-file") + 1])
text = query.read_text(encoding="utf-8")
task = re.search(r"task `([^`]+)`", text).group(1)
root = Path.cwd()
mode = os.environ.get("FAKE_MODE", "ok")
collab = root / "openspec/changes/demo/collab"
collab.mkdir(parents=True, exist_ok=True)
if mode != "no-evidence":
    (collab / f"{task}.md").write_text("evidence\\n", encoding="utf-8")
if mode != "no-done":
    (root / "done.txt").write_text("done\\n", encoding="utf-8")
if mode == "git":
    subprocess.run(["git", "commit", "-m", "x"], check=True)
"""


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def make_repo(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    root = tmp_path / "repo"
    change = root / "openspec" / "changes" / "demo"
    write(change / "tasks.md", "# Tasks\n\n- [ ] 1.1 Do the first thing\n- [ ] 1.2 Do the second thing\n")
    write(
        change / "routing.yaml",
        'schema: 1\nchange: demo\ntasks:\n'
        '  "1.1":\n    type: feature\n    verify:\n      - test -f done.txt\n'
        '  "1.2":\n    type: feature\n    verify:\n      - test -f done.txt\n',
    )
    write(change / "proposal.md", "# Proposal\n")
    write(change / "design.md", "# Design\n")
    write(change / "specs" / "demo" / "spec.md", "## ADDED Requirements\n")
    fake = root / "fake-hermes"
    fake.write_text(FAKE.replace("#!/usr/bin/env python3", f"#!{sys.executable}", 1), encoding="utf-8")
    fake.chmod(0o755)
    home = root / "hermes-home"
    write(home / "profiles" / "council-generalist" / "config.yaml", "model:\n  default: fake\n")
    return root, change, fake, home


def run_tool(root: Path, change: Path, fake: Path, home: Path, *extra: str,
             mode: str = "ok", command: str = "run") -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["FAKE_MODE"] = mode
    return subprocess.run(
        [
            sys.executable,
            str(TOOL),
            command,
            "--change",
            str(change),
            "--repo",
            str(root),
            "--hermes",
            str(fake),
            "--hermes-home",
            str(home),
            *extra,
        ],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )


def tasks_text(change: Path) -> str:
    return (change / "tasks.md").read_text(encoding="utf-8")


def test_a_passing_task_is_ticked_only_after_its_predicate(tmp_path: Path) -> None:
    root, change, fake, home = make_repo(tmp_path)
    result = run_tool(root, change, fake, home, "--limit", "1")
    assert result.returncode == 0, result.stderr
    assert "- [x] 1.1 Do the first thing" in tasks_text(change)
    assert "- [ ] 1.2 Do the second thing" in tasks_text(change)
    assert (change / "collab" / "1.1.md").is_file()
    assert (change / "collab" / "prompts" / "1.1.md").is_file()
    assert "passed and ticked" in result.stdout
    assert "commit -m" in result.stdout


def test_a_failing_predicate_leaves_the_task_unticked(tmp_path: Path) -> None:
    root, change, fake, home = make_repo(tmp_path)
    result = run_tool(root, change, fake, home, mode="no-done")
    assert result.returncode == 1
    assert "- [ ] 1.1 Do the first thing" in tasks_text(change)
    assert "predicate failed" in result.stdout


def test_missing_evidence_stops_before_the_predicate(tmp_path: Path) -> None:
    root, change, fake, home = make_repo(tmp_path)
    result = run_tool(root, change, fake, home, mode="no-evidence")
    assert result.returncode == 1
    assert "missing or empty" in result.stdout
    assert "- [ ] 1.1 Do the first thing" in tasks_text(change)


def test_the_worker_cannot_git_commit(tmp_path: Path) -> None:
    root, change, fake, home = make_repo(tmp_path)
    result = run_tool(root, change, fake, home, mode="git")
    assert result.returncode == 1
    assert "refusing git commit" in result.stdout
    assert "- [ ] 1.1 Do the first thing" in tasks_text(change)


def test_plan_does_not_call_the_worker(tmp_path: Path) -> None:
    root, change, fake, home = make_repo(tmp_path)
    result = run_tool(root, change, fake, home, command="plan")
    assert result.returncode == 0, result.stderr
    assert "1.1  Do the first thing" in result.stdout
    assert "predicate: test -f done.txt" in result.stdout
    assert "[type:" not in result.stdout
    assert not (root / "done.txt").exists()
    assert not (change / "collab" / "1.1.md").exists()


def test_a_missing_profile_is_refused_before_the_worker(tmp_path: Path) -> None:
    root, change, fake, home = make_repo(tmp_path)
    (home / "profiles" / "council-generalist" / "config.yaml").unlink()
    result = run_tool(root, change, fake, home)
    assert result.returncode == 1
    assert "hermes profile create" in result.stderr
    assert not (root / "done.txt").exists()


def test_a_dry_run_does_not_write(tmp_path: Path) -> None:
    root, change, fake, home = make_repo(tmp_path)
    result = run_tool(root, change, fake, home, "--dry-run")
    assert result.returncode == 0, result.stderr
    assert "would run:" in result.stdout
    assert "- [ ] 1.1 Do the first thing" in tasks_text(change)
    assert not (root / "done.txt").exists()


def test_a_missing_routing_map_is_refused(tmp_path: Path) -> None:
    root, change, fake, home = make_repo(tmp_path)
    (change / "routing.yaml").unlink()
    result = run_tool(root, change, fake, home)
    assert result.returncode == 1
    assert "no routing.yaml" in result.stderr
    assert not (root / "done.txt").exists()


def test_status_lists_predicates_and_evidence(tmp_path: Path) -> None:
    root, change, fake, home = make_repo(tmp_path)
    result = run_tool(root, change, fake, home, command="status")
    assert result.returncode == 0, result.stderr
    assert "predicate:" in result.stdout
    assert "1.2" in result.stdout


def test_an_inline_predicate_list_is_still_read(tmp_path: Path) -> None:
    root, change, fake, home = make_repo(tmp_path)
    (change / "routing.yaml").write_text(
        'schema: 1\nchange: demo\ntasks:\n'
        '  "1.1":\n    type: feature\n    verify: ["test -f done.txt"]\n'
        '  "1.2":\n    type: feature\n    verify: ["test -f done.txt"]\n',
        encoding="utf-8",
    )
    result = run_tool(root, change, fake, home, command="plan")
    assert result.returncode == 0, result.stderr
    assert "predicate: test -f done.txt" in result.stdout
