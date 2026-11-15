"""Prove the suite can fail: mutate the rule, expect the tests to catch it.

A test that survives a mutation is decorative — it asserts something the code
does anyway. This runs a set of deliberate breakages against a scratch copy of
`src/`, and fails if any of them passes the suite.

It also ties each mutation to the claims it breaks: a claim may name its
`falsifier`, and every mutation must falsify at least one claim. Both directions
are checked, so a check that cannot fail and a mutation nobody notices are both
visible.

Usage:
    python3 tools/mutation_check.py

Exit 0 when every mutation is caught, every declared falsifier breaks its claim,
and every mutation falsifies at least one claim.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from council.claims import load as load_claims  # noqa: E402

NODE = re.compile(r"(tests/[\w./-]+\.py::[\w\[\]-]+)")


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
    Mutation("absent-ignores-within",
             "proofs.py",
             "if within and not any(fnmatch.fnmatch(rel, glob) for glob in within):",
             "if False:"),
    Mutation("repro-passes-on-success",
             "proofs.py", "if ran.returncode == 0:", "if False:"),
    Mutation("digest-ignores-the-profile-config",
             "prompt.py",
             'profile_fingerprint or "profile-config:unknown", *dimensions):',
             "*dimensions):"),
    Mutation("diff-context-not-counted",
             "changes.py",
             'if prefix == " ":\n                old_line += 1\n                new_line += 1\n                old_left -= 1\n                new_left -= 1',
             'if prefix == " ":\n                old_left -= 1\n                new_left -= 1'),
    Mutation("config-ignores-unknown-keys",
             "domain/config.py", "if unknown:", "if False:"),
    Mutation("merge-takes-the-lowest-severity",
             "merge.py", "highest = max(entries, key=lambda entry: _RANK[entry[1].severity])",
             "highest = min(entries, key=lambda entry: _RANK[entry[1].severity])"),
    Mutation("a-missing-sample-can-still-pass",
             "domain/adjudication.py",
             "if adjudication.failed_samples:",
             "if False:"),
    Mutation("report-mode-is-ignored",
             "cli.py", "return 0 if args.report else report.exit_code",
             "return report.exit_code"),
    Mutation("a-usage-error-reuses-the-incomplete-code",
             "cli_parser.py", "EXIT_ERROR = 3", "EXIT_ERROR = 2"),
    Mutation("a-run-may-overwrite-an-old-one",
             "runstore.py", "directory.mkdir(parents=True, exist_ok=False)",
             "directory.mkdir(parents=True, exist_ok=True)"),
    Mutation("failed-samples-are-forgotten",
             "run.py", "failed_samples=[sample.index for sample in runs[0][1] if not sample.ok])",
             "failed_samples=[]),"),
    Mutation("slicing-disabled",
             "prepare.py", "sliced = prompt_bytes > request.max_prompt_bytes and not request.allow_large_prompt",
             "sliced = False"),
    Mutation("a-missing-prompt-is-not-refused",
             "prepare.py", "if not prompt_file.is_file():", "if False:"),
    Mutation("config-parsing-reads-a-file",
             "domain/config.py",
             "return Config(allow=allow, timeout=timeout, sandbox=policy.sandbox or sandbox)",
             'return __import__("pathlib").Path(name).read_text()'),
    Mutation("baseline-suppresses-open-findings",
             "domain/baseline.py",
             "for finding in result.findings:\n        if finding.state is not State.PROVEN or not finding.blocks:",
             "for finding in result.findings:\n        if not finding.blocks:"),
    Mutation("baseline-ignores-expiry",
             "domain/baseline.py",
             "if today > entry.expires:",
             "if False:"),
    Mutation("baseline-may-be-edited",
             "prepare.py",
             "if _baseline_changed(request, change.patch) and not request.allow_baseline_change:",
             "if False:"),
    Mutation("baseline-forgets-missing-evidence",
             "domain/baseline.py",
             "if fresh.verdict is Verdict.PASS and missing_evidence:",
             "if False:"),
    Mutation("scope-ignores-excludes",
             "domain/scope.py",
             "if excluded is not None:",
             "if False:"),
    Mutation("scope-ignores-includes",
             "domain/scope.py",
             "if self.includes:",
             "if False:"),
    Mutation("scope-drops-without-recording",
             "domain/scope.py",
             "ignored.append(ScopeIgnored(section.path, decision.reason,\n                                            decision.pattern))",
             "pass"),
    Mutation("scope-pattern-validation-disabled",
             "domain/scope.py",
             "def _validate(pattern: str) -> None:",
             "def _validate(pattern: str) -> None:\n    return"),
    Mutation("staged-reads-worktree",
             "repo.py",
             "if staged:\n        return Change(tracked)",
             "if False:\n        return Change(tracked)"),
    Mutation("scope-empty-passes",
             "prepare.py",
             "if not patch.strip():",
             "if False:"),
)


def claim_node(check: str) -> str | None:
    """The pytest node a claim cites, if it cites one."""
    match = NODE.search(check)
    return match.group(1) if match else None


def failing_tests(report: Path) -> set[str]:
    broken: set[str] = set()
    for case in ET.parse(report).iter("testcase"):
        if case.find("failure") is None and case.find("error") is None:
            continue
        module = case.get("classname", "").replace(".", "/")
        if module and not module.endswith(".py"):
            module = f"{module}.py"
        broken.add(f"{module}::{case.get('name', '')}")
    return broken


def run_suite(src: Path) -> tuple[int, set[str]]:
    """Run the suite against a mutated tree; return the exit code and failing node ids."""
    with tempfile.TemporaryDirectory() as raw:
        report = Path(raw) / "junit.xml"
        code = subprocess.run(
            [sys.executable, "-m", "pytest", "-o", f"pythonpath={src}", "-q", "--no-header",
             "-p", "no:cacheprovider", f"--junitxml={report}"],
            cwd=ROOT, capture_output=True, text=True,
        ).returncode
        return code, failing_tests(report) if report.exists() else set()


def main() -> int:
    claims = load_claims(ROOT / "claims.toml")
    by_node = {claim_node(claim.check): claim for claim in claims if claim_node(claim.check)}

    survivors: list[str] = []
    falsified: dict[str, set[str]] = {}
    for mutation in MUTATIONS:
        with tempfile.TemporaryDirectory(prefix="council-mut-") as raw:
            src = Path(raw) / "src"
            shutil.copytree(ROOT / "src", src)
            # A copied tree can keep its source permissions (a store path or a
            # read-only checkout); the mutations have to be writable.
            for path in [src, *src.rglob("*")]:
                path.chmod(0o755 if path.is_dir() else 0o644)
            target = src / "council" / mutation.file
            text = target.read_text(encoding="utf-8")
            if mutation.old not in text:
                print(f"  STALE  {mutation.name}: pattern not found in {mutation.file}")
                survivors.append(mutation.name)
                falsified[mutation.name] = set()
                continue
            target.write_text(text.replace(mutation.old, mutation.new, 1), encoding="utf-8")
            code, broken = run_suite(src)
            caught = code != 0
            print(f"  {'caught' if caught else 'SURVIVED'}  {mutation.name}")
            if not caught:
                survivors.append(mutation.name)
            hit = {by_node[node].id for node in broken if node in by_node}
            falsified[mutation.name] = hit
            if hit:
                print(f"            falsifies {', '.join(sorted(hit))}")

    problems: list[str] = []
    for claim in claims:
        if claim.falsifier is None:
            continue
        if claim.falsifier not in falsified:
            problems.append(f"{claim.id}: falsifier {claim.falsifier!r} is not a mutation")
        elif claim.id not in falsified[claim.falsifier]:
            problems.append(f"{claim.id}: falsifier {claim.falsifier!r} did not break it")
    for mutation in MUTATIONS:
        if not falsified[mutation.name]:
            problems.append(f"mutation {mutation.name!r} falsifies no claim")

    total = len(MUTATIONS)
    declared = sum(1 for claim in claims if claim.falsifier is not None)
    print(f"\n{total - len(survivors)}/{total} mutations caught; "
          f"{declared} claim(s) declare a falsifier")
    for problem in problems:
        print(f"  PROBLEM {problem}")
    return 0 if not survivors and not problems else 1


if __name__ == "__main__":
    raise SystemExit(main())
