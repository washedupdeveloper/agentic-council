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

import argparse
import concurrent.futures
import hashlib
import json
import os
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

from council.claims import Claim, load as load_claims  # noqa: E402

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
             "domain/verdict.py",
             "unsettled_quoted = quoted if executed_only else []",
             "unsettled_quoted = []"),
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
             "proofs.py",
             'return _failed(f"{\' \'.join(argv)} exited 0: the defect did not reproduce")',
             'return _held(f"{\' \'.join(argv)} exited 0: the defect did not reproduce")'),
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
    Mutation("strict-fail-hides-quotation",
             "domain/verdict.py",
             "if quoted and executed_only:",
             "if False:"),
    Mutation("doctor-source-version-ignored",
             "doctor.py",
             "if installed == source_version:",
             "if True:"),
    Mutation("single-sample-opt-in-ignored",
             "request.py",
             "if self.samples == 1 and not self.allow_single_sample:",
             "if False:"),
)


def claim_node(check: str) -> str | None:
    """The pytest node a claim cites, if it cites one."""
    match = NODE.search(check)
    return match.group(1) if match else None


def falsifier_nodes(claims: list[Claim]) -> dict[str, list[str]]:
    """Map each mutation to the pytest nodes of the claims that name it as falsifier.

    Those claims are the only ones a mutant's verdict can settle, so their nodes are the
    smallest run that can still prove a catch -- 1.11 nodes on average for this registry.
    """
    mapping: dict[str, list[str]] = {}
    for claim in claims:
        if claim.falsifier is None:
            continue
        node = claim_node(claim.check)
        if node is not None and node not in mapping.setdefault(claim.falsifier, []):
            mapping[claim.falsifier].append(node)
    return mapping


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


def run_suite(src: Path, nodes: list[str] | None = None,
              failfast: bool = False) -> tuple[int, set[str]]:
    """Run the suite against a mutated tree; return the exit code and failing node ids.

    `nodes` restricts the run and `failfast` stops at the first failure. Both exist for
    one reason: the campaign asks whether a mutant was noticed, and the mutant's own
    declared falsifier answers that in about a second against the suite's twenty-seven.
    A pass here proves nothing -- the caller falls back to the full suite for that.
    """
    with tempfile.TemporaryDirectory() as raw:
        report = Path(raw) / "junit.xml"
        # A private temp root and basetemp per suite: twelve of these run at once,
        # and pytest prunes numbered basetemps under whatever TMPDIR it inherits.
        # Sharing one lets two suites delete each other's directories mid-scan, and
        # its cleanup leaves a scandir handle that warns from its finaliser -- an
        # error under `filterwarnings = ["error"]`, reported against a mutant that
        # had nothing to do with it. With a basetemp the numbered path never runs.
        env = {**os.environ, "TMPDIR": raw, "TMP": raw, "TEMP": raw}
        code = subprocess.run(
            [sys.executable, "-m", "pytest", "-o", f"pythonpath={src}", "-q", "--no-header",
             "-p", "no:cacheprovider", f"--basetemp={Path(raw) / 'base'}",
             *(["-x", "--tb=no"] if failfast else []), *(nodes or []),
             f"--junitxml={report}"],
            cwd=ROOT, capture_output=True, text=True, env=env,
        ).returncode
        return code, failing_tests(report) if report.exists() else set()


def _copy_src(raw: str) -> Path:
    src = Path(raw) / "src"
    shutil.copytree(ROOT / "src", src)
    for path in [src, *src.rglob("*")]:
        path.chmod(0o755 if path.is_dir() else 0o644)
    return src


def mutation_names() -> list[str]:
    """Every mutant, in registry order."""
    return [mutation.name for mutation in MUTATIONS]


def _select(names: list[str] | None) -> tuple[Mutation, ...]:
    if not names:
        return MUTATIONS
    wanted = set(names)
    chosen = tuple(m for m in MUTATIONS if m.name in wanted)
    unknown = wanted - {m.name for m in chosen}
    if unknown:
        raise SystemExit(f"no such mutation: {', '.join(sorted(unknown))}")
    return chosen


def _parse_shard(raw: str) -> tuple[int, int]:
    """"I/N" -> the I-th of N interleaved slices of the registry."""
    head, _, tail = raw.partition("/")
    try:
        index, count = int(head), int(tail)
    except ValueError:
        raise SystemExit(f"--shard wants I/N, got {raw!r}") from None
    if count < 1 or not 0 <= index < count:
        raise SystemExit(f"--shard wants 0 <= I < N, got {raw!r}")
    return index, count


def _shard(mutations: tuple[Mutation, ...], index: int, count: int) -> tuple[Mutation, ...]:
    """Interleaved, so each slice gets a spread of files rather than one region."""
    return tuple(m for i, m in enumerate(mutations) if i % count == index)


def tree_digest() -> str:
    """Every input that can change a verdict, hashed into one string.

    The campaign's unit is "run the whole suite under this mutation", so a change
    anywhere in `src/` or `tests/` can change any verdict -- not only the file a mutant
    touches. The digest covers both trees, the registry, this tool and the interpreter,
    and claims nothing broader: an identical digest means an identical experiment.
    """
    h = hashlib.sha256()
    h.update(sys.version.encode())
    for base in (ROOT / "src", ROOT / "tests"):
        for path in sorted(base.rglob("*")):
            if not path.is_file() or "__pycache__" in path.parts:
                continue
            h.update(str(path.relative_to(ROOT)).encode())
            h.update(hashlib.sha256(path.read_bytes()).digest())
    for extra in (ROOT / "claims.toml", Path(__file__).resolve()):
        h.update(extra.name.encode())
        h.update(hashlib.sha256(extra.read_bytes()).digest())
    return h.hexdigest()


def load_cache(path: Path) -> dict[str, dict[str, list[object]]]:
    """The recorded verdicts, keyed by tree digest. An unreadable cache is an empty one."""
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


def save_cache(path: Path, cache: dict[str, dict[str, list[object]]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(cache, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


def _score(mutation: Mutation, by_node: dict[str, list[str]],
           falsifier_nodes: list[str], fast: bool = True
           ) -> tuple[str, bool, set[str], str | None, bool]:
    """Score one mutant: its own falsifier first, the whole suite only to prove a miss.

    Returns (name, caught, claims-broken, problem, decided_by_falsifier). The subset is
    the pytest nodes of the claims that name this mutant as their falsifier -- the only
    claims its verdict can settle, and the smallest run that can still prove a catch. A
    failure there is a real failure, so `caught` needs no inference; a pass proves
    nothing, so the full suite runs and decides. That asymmetry is the whole guarantee:
    a subset may prove a catch, only the whole suite may prove a miss.
    """
    with tempfile.TemporaryDirectory(prefix="council-mut-") as raw:
        src = _copy_src(raw)
        target = src / "council" / mutation.file
        body = target.read_text(encoding="utf-8")
        if mutation.old not in body:
            return mutation.name, False, set(), f"pattern not found in {mutation.file}", False
        target.write_text(body.replace(mutation.old, mutation.new, 1), encoding="utf-8")
        if fast and falsifier_nodes:
            # Every falsifier node runs: a mutant can be named by two or three claims, and
            # stopping at the first failure would report only that one as broken -- the
            # others would look like claims their own falsifier failed to break.
            subset_code, subset_broken = run_suite(src, nodes=falsifier_nodes)
            if subset_code != 0:
                broken = subset_broken
                hit = {claim_id for node in broken for claim_id in by_node.get(node, [])}
                return mutation.name, True, hit, None, True
            print(f"  fallback  {mutation.name}: its declared falsifier did not fire", flush=True)
        code, broken = run_suite(src)
    hit = {claim_id for node in broken for claim_id in by_node.get(node, [])}
    return mutation.name, code != 0, hit, None, False


def main(argv: list[str] | None = None) -> int:
    # `argv=None` means "the campaign, as a library call": a test that imports
    # this module must not be given pytest's own command line.
    parser = argparse.ArgumentParser(
        prog="mutation_check",
        description="Break each rule on purpose and prove the suite notices.")
    parser.add_argument(
        "--list", action="store_true",
        help="print every mutation name and exit")
    parser.add_argument(
        "--only", action="append", metavar="NAME",
        help="score only this mutation (repeatable); the whole registry is the default")
    parser.add_argument(
        "--shard", metavar="I/N", default=None,
        help="score the I-th of N interleaved slices; CI runs one job per slice")
    parser.add_argument(
        "--no-fast", action="store_true",
        help="run the whole suite for every mutant instead of its declared falsifier first")
    parser.add_argument(
        "--cache", type=Path, default=ROOT / ".council" / "mutation-cache.json",
        help="reuse verdicts recorded for a byte-identical tree (default: .council/)")
    parser.add_argument(
        "--no-cache", action="store_true",
        help="score every mutant, ignoring and not writing the cache")
    parser.add_argument(
        "--jobs", type=int, default=0, metavar="N",
        help="score this many mutants at once (0 = one per core)")
    args = parser.parse_args(argv) if argv is not None else None

    if args is not None and args.list:
        for name in mutation_names():
            print(name)
        return 0

    selected = _select(args.only if args is not None else None)
    shard = _parse_shard(args.shard) if args is not None and args.shard else None
    if shard is not None:
        whole = len(selected)
        selected = _shard(selected, *shard)
        print(f"shard {shard[0]}/{shard[1]}: {len(selected)} of {whole} mutant(s)", flush=True)
    claims = load_claims(ROOT / "claims.toml")
    nodes_by_mutant = falsifier_nodes(claims)
    by_node: dict[str, list[str]] = {}
    for claim in claims:
        node = claim_node(claim.check)
        if node is not None:
            by_node.setdefault(node, []).append(claim.id)

    cache_path = None if args is None or args.no_cache else args.cache
    digest = tree_digest() if cache_path is not None else ""
    cache = load_cache(cache_path) if cache_path is not None else {}
    recorded = cache.get(digest, {})
    selected_names = {mutation.name for mutation in selected}
    cached: dict[str, tuple[bool, set[str], str | None]] = {}
    for name, value in recorded.items():
        if name not in selected_names or not isinstance(value, list) or len(value) != 3:
            continue
        caught, broken, problem = value
        cached[name] = (
            caught if isinstance(caught, bool) else False,
            {str(node) for node in broken} if isinstance(broken, list) else set(),
            problem if isinstance(problem, str) else None,
        )
    to_score = [m for m in selected if m.name not in cached]
    if cached:
        print(f"{len(cached)} of {len(selected)} mutant(s) answered by the cache for this tree",
              flush=True)

    # The baseline proves the unmutated suite passes *now*. A tree identical to the one
    # that already produced these verdicts cannot have changed that, so with nothing left
    # to score it is not paid for again.
    if to_score:
        with tempfile.TemporaryDirectory(prefix="council-baseline-") as raw:
            baseline_src = _copy_src(raw)
            baseline_code, baseline_broken = run_suite(baseline_src)
    else:
        baseline_code, baseline_broken = 0, set()
    if baseline_code != 0:
        print("BASELINE RED: the unmodified suite must pass before mutations are scored")
        for node in sorted(baseline_broken):
            print(f"  {node}")
        return 1

    survivors: list[str] = []
    falsified: dict[str, set[str]] = {}

    # One worker per core by default, `--jobs N` to say otherwise. A pool decides
    # scheduling only. The suite is the same, the mutants are the same, and every
    # mutant must still be caught -- so the campaign proves exactly what it did
    # serially, in a fraction of the wall clock.
    #
    # This read `MUTATION_WORKERS` from the environment while the claim registry read
    # `--jobs`: one policy value, two mechanisms, and nothing on the command line said
    # what the pool size would be. A policy value is a flag.
    default_workers = os.cpu_count() or 2
    requested = args.jobs if args is not None else 0
    workers = max(1, min(len(to_score), requested or default_workers)) if to_score else 1
    scored: dict[str, tuple[bool, set[str], str | None]] = {}
    fast_count: list[str] = []
    slow_count: list[str] = []
    if to_score:
        print(f"scoring {len(to_score)} mutant(s) across {workers} worker(s)", flush=True)
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(_score, m, by_node, nodes_by_mutant.get(m.name, []),
                                   not (args is not None and args.no_fast)): m
                       for m in to_score}
            for future in concurrent.futures.as_completed(futures):
                name, caught, hit, problem, by_falsifier = future.result()
                if by_falsifier:
                    fast_count.append(name)
                else:
                    slow_count.append(name)
                scored[name] = (caught, hit, problem)
                if problem is not None:
                    print(f"  STALE  {name}: {problem}", flush=True)
                    continue
                print(f"  {'caught' if caught else 'SURVIVED'}  {name}", flush=True)
                if hit:
                    print(f"            falsifies {', '.join(sorted(hit))}", flush=True)

    results = {**cached, **scored}
    for mutation in selected:
        name = mutation.name
        caught, hit, problem = results[name]
        if problem is not None:
            survivors.append(name)
            falsified[name] = set()
            continue
        if not caught:
            survivors.append(name)
        falsified[name] = hit

    if to_score:
        print(f"{len(fast_count)} decided by the declared falsifier, "
              f"{len(slow_count)} by the full suite", flush=True)

    # Only the mutants scored in this run are recorded, merged into what the digest
    # already holds -- a shard must not erase its siblings' work.
    if cache_path is not None and scored:
        merged = dict(cache.get(digest, {}))
        for name, (caught, hit, problem) in scored.items():
            merged[name] = [caught, sorted(hit), problem]
        cache[digest] = merged
        try:
            save_cache(cache_path, cache)
        except OSError:
            # A read-only source tree (the Nix sandbox) is not a reason to fail a run:
            # the cache is an optimisation, and Nix already caches the whole derivation.
            print("cache: not writable here; verdicts not recorded", flush=True)

    problems: list[str] = []
    known = set(mutation_names())
    for claim in claims:
        if claim.falsifier is None:
            continue
        if claim.falsifier not in known:
            # A registry error, independent of which shard is running.
            problems.append(f"{claim.id}: falsifier {claim.falsifier!r} is not a mutation")
        elif claim.falsifier not in falsified:
            # Another shard owns this mutant; the union over 0..N-1 is every index
            # by construction, so nothing is dropped by skipping it here.
            continue
        elif claim.id not in falsified[claim.falsifier]:
            problems.append(f"{claim.id}: falsifier {claim.falsifier!r} did not break it")
    for mutation in selected:
        if not falsified[mutation.name]:
            problems.append(f"mutation {mutation.name!r} falsifies no claim")

    total = len(selected)
    declared = sum(1 for claim in claims if claim.falsifier is not None)
    owned = sum(1 for claim in claims if claim.falsifier in falsified)
    scope = f"; {owned}/{declared} falsifier claim(s) owned by this shard" if shard else ""
    print(f"\n{total - len(survivors)}/{total} mutations caught; "
          f"{declared} claim(s) declare a falsifier{scope}")
    for problem in problems:
        print(f"  PROBLEM {problem}")
    return 0 if not survivors and not problems else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
