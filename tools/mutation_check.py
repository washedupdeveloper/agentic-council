"""Prove the suite can fail: mutate the rule, expect the tests to catch it.

A test that survives a mutation is decorative — it asserts something the code
does anyway. This runs a small set of deliberate breakages against a scratch
copy of `src/`, and fails if any of them passes the suite.

Usage:
    python3 tools/mutation_check.py

Exit 0 when every mutation is caught. This is the check that would have caught
the two defects the v1 suite missed: a parser that only honoured the last hunk,
and a threshold that was printed but never compared.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True, slots=True)
class Mutation:
    name: str
    file: str
    old: str
    new: str


#: Each entry breaks exactly one rule. Keep them small: a mutation that breaks
#: three things proves only that the suite notices something.
MUTATIONS: tuple[Mutation, ...] = (
    Mutation("medium-becomes-blocking",
             "findings.py", 'frozenset({"high", "critical"})',
             'frozenset({"medium", "high", "critical"})'),
    Mutation("fail-branch-reads-refuted",
             "verdict.py", "f.state is State.PROVEN", "f.state is State.REFUTED"),
    Mutation("incomplete-branch-removed",
             "verdict.py", "if open_blocking:", "if False and open_blocking:"),
    Mutation("open-states-narrowed",
             "findings.py", 'frozenset({State.UNSETTLED, State.UNRUNNABLE})',
             'frozenset({State.UNSETTLED})'),
    Mutation("exit-code-swapped",
             "verdict.py", "Verdict.FAIL: 1, Verdict.INCOMPLETE: 2",
             "Verdict.FAIL: 2, Verdict.INCOMPLETE: 1"),
    Mutation("schema-accepts-a-zero-line",
             "schema.py", "if line < 1:", "if line < 0:"),
    Mutation("schema-accepts-a-missing-proof",
             "schema.py", 'proof = _field(entry, "proof", where, kind=dict)',
             'proof = entry.get("proof", {"kind": "absent", "params": {}})'),
    Mutation("sample-never-retries",
             "sample.py", "for attempt in range(1, attempts + 1):",
             "for attempt in range(1, 2):"),
    Mutation("proof-allowlist-disabled",
             "proofs.py", "if binary not in ctx.allow:", "if False:"),
    Mutation("diff-context-not-counted",
             "proofs.py",
             'elif raw.startswith(" "):\n            old_line += 1\n            new_line += 1',
             'elif raw.startswith(" "):\n            pass'),
    Mutation("config-ignores-unknown-keys",
             "config.py", "if unknown:", "if False:"),
    Mutation("merge-takes-the-lowest-severity",
             "merge.py", "highest = max(entries, key=lambda entry: _RANK[entry[1].severity])",
             "highest = min(entries, key=lambda entry: _RANK[entry[1].severity])"),
    Mutation("a-missing-sample-can-still-pass",
             "adjudicate.py",
             "if adjudication.failed_samples and result.verdict is Verdict.PASS:",
             "if False:"),
    Mutation("report-mode-is-ignored",
             "cli.py", "return 0 if args.report else report.exit_code",
             "return report.exit_code"),
    Mutation("a-usage-error-reuses-the-incomplete-code",
             "cli.py", "EXIT_ERROR = 3", "EXIT_ERROR = 2"),
    Mutation("a-run-may-overwrite-an-old-one",
             "run.py", "if directory.exists():", "if False:"),
    Mutation("failed-samples-are-forgotten",
             "run.py", "failed_samples=[sample.index for sample in samples if not sample.ok],",
             "failed_samples=[],"),
    Mutation("a-missing-prompt-is-not-refused",
             "run.py", "if not prompt_file.exists():", "if False:"),
)


def run_suite(src: Path) -> int:
    """Run the suite against a mutated source tree; return pytest's exit code."""
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-o", f"pythonpath={src}", "-q", "--no-header",
         "-p", "no:cacheprovider"],
        cwd=ROOT, capture_output=True, text=True,
    ).returncode


def main() -> int:
    survivors: list[str] = []
    for mutation in MUTATIONS:
        with tempfile.TemporaryDirectory(prefix="council-mut-") as raw:
            src = Path(raw) / "src"
            shutil.copytree(ROOT / "src", src)
            target = src / "council" / mutation.file
            text = target.read_text(encoding="utf-8")
            if mutation.old not in text:
                print(f"  STALE  {mutation.name}: pattern not found in {mutation.file}")
                survivors.append(mutation.name)
                continue
            target.write_text(text.replace(mutation.old, mutation.new, 1), encoding="utf-8")
            code = run_suite(src)
            caught = code != 0
            print(f"  {'caught' if caught else 'SURVIVED'}  {mutation.name}")
            if not caught:
                survivors.append(mutation.name)

    total = len(MUTATIONS)
    print(f"\n{total - len(survivors)}/{total} mutations caught")
    return 0 if not survivors else 1


if __name__ == "__main__":
    raise SystemExit(main())