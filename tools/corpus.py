"""Six rungs: three clean, three with a seeded defect. Plan, sample, collect.

Usage:
    python tools/corpus.py plan   /tmp/corpus
    python tools/corpus.py sample /tmp/corpus [--profile P]
    python tools/corpus.py collect /tmp/corpus
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

CLEAN = '''"""Toy service."""


def add(a, b):
    return a + b
'''

DEFECT = CLEAN + '''
API_KEY = "AKIAIOSFODNN7EXAMPLE"
DB_PASSWORD = "hunter2"
'''


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


def plan(root: Path) -> None:
    for level in (0, 1):
        for run in (1, 2, 3):
            rung = root / "rungs" / f"level-{level}-run-{run}"
            rung.mkdir(parents=True, exist_ok=True)
            _git(rung, "init", "-q")
            _git(rung, "config", "user.email", "corpus@example.invalid")
            _git(rung, "config", "user.name", "corpus")
            # Two commits minimum: a one-commit repo has no base, and the
            # review refuses rather than review the whole tree as a change.
            (rung / "README.md").write_text("# rung\n", encoding="utf-8")
            _git(rung, "add", "-A")
            _git(rung, "commit", "-qm", "scaffold")
            (rung / "app.py").write_text(CLEAN, encoding="utf-8")
            _git(rung, "add", "-A")
            _git(rung, "commit", "-qm", "clean")
            if level:
                (rung / "app.py").write_text(DEFECT, encoding="utf-8")
                _git(rung, "add", "-A")
                _git(rung, "commit", "-qm", "seeded defect")
            print(f"  {rung.name:16} {'defective' if level else 'clean'}")


def sample(root: Path, council: str, profile: str) -> None:
    """Run the rungs that have no verdict yet, keeping progress as it goes."""
    results_file = root / "results.json"
    results: dict[str, dict[str, object]] = (
        json.loads(results_file.read_text(encoding="utf-8")) if results_file.exists() else {})

    for rung in sorted((root / "rungs").iterdir()):
        expected = "fail" if "level-1" in rung.name else "pass"
        verdict_file = rung / ".council" / "runs" / "sample-1" / "verdict.json"
        error = ""
        if not verdict_file.exists():
            argv = [council, "review", "-C", str(rung), "--samples", "1",
                    "--run-id", "sample-1", "--profile", profile, "--report"]
            try:
                proc = subprocess.run(argv, capture_output=True, text=True)
                error = proc.stderr.strip()[-200:]
            except OSError as exc:
                error = f"{type(exc).__name__}: {exc}"
        data = json.loads(verdict_file.read_text(encoding="utf-8")) \
            if verdict_file.exists() else {"verdict": "error" if error else "no-run", "findings": []}
        results[rung.name] = {"expected": expected, "got": data["verdict"],
                              "findings": len(data["findings"]), "stderr": error}
        results_file.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
        print(f"  {rung.name:16} expected {expected:5} got {data['verdict']:11} "
              f"findings {len(data['findings'])} {error[:60]}")


def collect(root: Path) -> int:
    results = json.loads((root / "results.json").read_text(encoding="utf-8"))
    wrong = [name for name, row in results.items() if row["got"] != row["expected"]]
    for name, row in sorted(results.items()):
        mark = "ok  " if row["got"] == row["expected"] else "FAIL"
        print(f"  {mark} {name:16} {row['got']:11} findings {row['findings']}")
    print(f"\n{len(results) - len(wrong)}/{len(results)} rungs correct")
    return 0 if not wrong else 1


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    root = Path(argv[1])
    if argv[0] == "plan":
        plan(root)
        return 0
    if argv[0] == "sample":
        profile = argv[argv.index("--profile") + 1] if "--profile" in argv else "council-generalist"
        sample(root, os.environ.get("COUNCIL", "council"), profile)
        return 0
    if argv[0] == "collect":
        return collect(root)
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
