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
             "domain/findings.py", 'frozenset({"high", "critical"})',
             'frozenset({"medium", "high", "critical"})'),
    Mutation("fail-branch-reads-refuted",
             "domain/verdict.py", "f.state is State.PROVEN", "f.state is State.REFUTED"),
    Mutation("incomplete-branch-removed",
             "domain/verdict.py",
             "    open_blocking = [f for f in items if f.blocks and f.state in OPEN_STATES]",
             "    open_blocking = []"),
    Mutation("open-states-narrowed",
             "domain/findings.py", 'frozenset({State.UNSETTLED, State.UNRUNNABLE})',
             'frozenset({State.UNSETTLED})'),
    Mutation("exit-code-swapped",
             "domain/verdict.py", "Verdict.FAIL: 1, Verdict.INCOMPLETE: 2",
             "Verdict.FAIL: 2, Verdict.INCOMPLETE: 1"),
    Mutation("schema-accepts-a-zero-line",
             "domain/schema.py", "if line < 1:", "if line < 0:"),
    Mutation("schema-accepts-a-missing-proof",
             "domain/schema.py", 'proof = _field(entry, "proof", where, kind=dict)',
             'proof = entry.get("proof", {"kind": "absent", "params": {}})'),
    Mutation("window-accounting-ignores-the-rules",
             "planning.py", "    overhead = prompt_overhead(template, base, references, rules)",
             "    overhead = prompt_overhead(template, base, references, '')"),
    Mutation("rules-never-reach-the-prompt",
             "planning.py", "(rules, context.text, reference_text(references))",
             "('', context.text, reference_text(references))"),
    Mutation("missing-rule-document-passes",
             "planning.py", "        if text is None:", "        if False:"),
    Mutation("rule-document-uncapped",
             "planning.py", "        if truncated:\n            text =",
             "        if False:\n            text ="),
    Mutation("findings-lose-their-evidence",
             "runstore.py", '"evidence": list(finding.evidence)}', '"evidence": []}'),
    Mutation("verdict-drops-claims",
             "runstore.py", '"claims": list(finding.claims),', '"claims": [finding.claim],'),
    Mutation("skill-declares-a-flag-the-cli-lacks",
             "cli_parser.py", '"--library"', '"--libraries"'),
    Mutation("merge-keys-on-dimension",
             "domain/merge.py",
             "            key = (finding.file, finding.line, _claim_key(finding.claim))",
             "            key = (finding.dimension, finding.file, finding.line, _claim_key(finding.claim))"),
    Mutation("merge-keys-on-place",
             "domain/merge.py",
             "            key = (finding.file, finding.line, _claim_key(finding.claim))",
             "            key = (finding.file, finding.line)"),
    Mutation("auto-clean-returns-first-sample",
             "sampling.py",
             "        second = run_sample(prompt, runner, index=2)",
             "        return (first,), 1, True"),
    Mutation("auto-second-finding-is-ignored",
             "sampling.py",
             "        if not second.output.findings:\n            return tuple(results), 2, True\n",
             "        if True:\n            return tuple(results), 2, True\n"),
    Mutation("auto-failed-confirmation-passes",
             "sampling.py",
             "        if second.output is None:\n            return tuple(results), 2, None",
             "        if second.output is None:\n            return tuple(results), 2, True"),
    Mutation("executed-only-accepts-quotation",
             "domain/verdict.py", "if executed_only:", "if False:"),
    Mutation("scope-report-unbounded",
             "runstore.py", "return listed[:limit], max(0, len(listed) - limit)",
             "return listed, 0"),
    Mutation("format-field-dropped",
             "runstore.py", '"format": VERDICT_FORMAT,', '"format": 0,'),
    Mutation("present-ignores-the-quote",
             "proofs.py", "if actual.strip() == expected.strip():", "if True:"),
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
    Mutation("window-bounds-ignore-the-budget",
             "planning.py", "if total + size > room and index > start:", "if False:"),
    Mutation("windows-never-refused",
             "planning.py", "if not request.window_large_files:", "if False:"),
    Mutation("digest-ignores-the-profile-config",
             "domain/prompt.py",
             'agent_fingerprint or profile_fingerprint or "profile-config:unknown",',
             'agent_fingerprint or "profile-config:unknown",'),
    Mutation("registry-forgets-hermes",
             "agents/__init__.py",
             "BUILTIN: tuple[AgentAdapter, ...] = (HermesAdapter(), DirectAdapter())",
             "BUILTIN: tuple[AgentAdapter, ...] = (DirectAdapter(),)"),
    Mutation("unknown-agent-falls-back",
             "agents/__init__.py",
             'raise ValueError(\n                f"unknown reviewer agent {name!r}; available: {available}"\n            ) from exc',
             "return next(iter(self._adapters.values()))"),
    Mutation("verdict-forgets-agent",
             "runstore.py",
             '"agent": request.agent,',
             '"agent": "hermes",'),
    Mutation("cli-ignores-agent",
             "cli.py",
             'agent=args.agent, reviewer=args.reviewer or "",',
             'agent="hermes", reviewer=args.reviewer or "",'),
    Mutation("agent-default-is-hardcoded",
             "cli.py",
             "binary = args.reviewer or selected.default_binary",
             'binary = args.reviewer or "hermes"'),
    Mutation("server-ignores-agent",
             "../council_server/cli.py",
             'argv.extend(["--agent", config.agent])',
             'argv.extend(["--agent", "hermes"])'),
    Mutation("digest-ignores-agent",
             "domain/prompt.py",
             'for part in ("council-prompt-v2", agent, contract, template, profile,',
             'for part in ("council-prompt-v2", contract, template, profile,'),
    Mutation("evidence-stores-an-absolute-path",
             "artifacts.py",
             'entry = Artifact(f"{ARTIFACTS}/{name}", digest, len(data),',
             'entry = Artifact(str(target), digest, len(data),'),
    Mutation("evidence-hides-a-missing-file",
             "artifacts.py",
             '"missing": not target.is_file(),',
             '"missing": False,'),
    Mutation("evidence-link-is-blank",
             "artifacts.py",
             'return f"[{label}]({link(run_dir, artifact)})"',
             'return f"[{label}]()"'),
    Mutation("diff-context-not-counted",
             "domain/changes.py",
             'for line in hunk.body:\n                prefix = line[:1]\n                if prefix == " ":\n                    old_line += 1\n                    new_line += 1',
             'for line in hunk.body:\n                prefix = line[:1]\n                if prefix == " ":\n                    old_line += 1'),
    Mutation("config-ignores-unknown-keys",
             "domain/config.py", "if unknown:", "if False:"),
    Mutation("merge-takes-the-lowest-severity",
             "domain/merge.py", "highest = max(entries, key=lambda entry: _RANK[entry[1].severity])",
             "highest = min(entries, key=lambda entry: _RANK[entry[1].severity])"),
    Mutation("units-that-never-ran-pass",
             "run.py", "silent = [run.unit.id for run in unreviewed if run.error is None]",
             "silent = []"),
    Mutation("a-unit-row-loses-a-key",
             "runstore.py", '"samples_run": run.samples_run,\n        "agreement": run.agreement,',
             '"samples_run": run.samples_run,'),
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
             "run.py", "failed_samples=[sample.index for sample in runs[0].samples if not sample.ok])",
             "failed_samples=[]),"),
    Mutation("slicing-disabled",
             "prepare.py", "sliced = prompt_bytes > request.max_prompt_bytes and not request.allow_large_prompt",
             "sliced = False"),
    Mutation("a-missing-prompt-is-not-refused",
             "prepare.py", "if not prompt_file.is_file():", "if False:"),
    Mutation("config-parsing-reads-a-file",
             "domain/config.py",
             'return Config(allow=allow, timeout=timeout, sandbox=policy.sandbox or sandbox,\n'
             '                  rules=rules)',
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
    Mutation("pr-target-is-ignored",
             "pr.py",
             "ref = _target(target)",
             'ref = "7"'),
    Mutation("pr-cli-target-is-ignored",
             "cli.py",
             "pr: PullRequest = resolve_pr(args.target, args.repo)",
             "pr: PullRequest = resolve_pr(7, args.repo)"),
    Mutation("mcp-review-always-passes",
             "../council_mcp/server.py",
             '"verdict": payload.get("verdict"),',
             '"verdict": "pass",'),
    Mutation("acp-commands-are-not-advertised",
             "../council_acp/agent.py",
             "asyncio.create_task(self._announce_commands(session_id))",
             "pass"),
    Mutation("acp-prefixes-are-not-cleaned",
             "../council_acp/agent.py",
             "await self._send(session_id, _clean_message(str(exc)))",
             "await self._send(session_id, f\"council: {exc}\")"),
    Mutation("sandbox-reviewer-keeps-symlink",
             "runner.py",
             "binary = str(Path(located).resolve())",
             "binary = located"),
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
    by_node: dict[str, list[str]] = {}
    for claim in claims:
        node = claim_node(claim.check)
        if node is not None:
            by_node.setdefault(node, []).append(claim.id)

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
            hit = {claim_id for node in broken for claim_id in by_node.get(node, [])}
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
