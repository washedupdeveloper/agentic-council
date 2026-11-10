"""One review: request in, written run out. The runner is a parameter."""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .adjudicate import adjudicate, verdict
from .base import resolve_base
from .changes import file_sections, hunk_range, hunk_sections
from .config import CONFIG_NAME, load as load_config
from .context import Context, build as build_context
from .findings import OPEN_STATES, Finding, State, blocks
from .merge import merge
from .paths import run_dir as run_path
from .prompt import instrument_digest, render
from .proofs import ProofContext
from .reference import FetchError, Reference, fetch
from .repo import (ReviewError, Skipped, diff, output, python_files,
                   root as repo_root, state_dir_ignored)
from .sample import Runner, SampleResult, run_sample, write_sample
from .schema import RawFinding
from .verdict import Result, Verdict

DEFAULT_PROFILE = "council-generalist"
AUTO_MAX = 3
# A prompt past this size is not sent to the reviewer without a person's word.
# The failure is silent and expensive otherwise: the model can sit for its whole
# timeout and the sample is retried once.
PROMPT_LIMIT = 32 * 1024


class PromptTooLarge(ReviewError):
    """The prompt is over the limit and nobody has allowed it."""

    def __init__(self, size: int, limit: int, *, declined: bool = False,
                 unit: str | None = None) -> None:
        self.size = size
        self.limit = limit
        self.unit = unit
        if declined:
            tail = "Nothing was asked: proceeding was declined."
        else:
            tail = ("Nothing was asked. Narrow the change with --base, raise the "
                    "budget with --max-prompt-bytes, or allow it with "
                    "--allow-large-prompt.")
        where = f" for {unit}" if unit else ""
        super().__init__(
            f"the prompt{where} is {size:,} bytes; the limit is {limit:,}. {tail}")


def default_prompt() -> Path:
    """The instrument ships with the tool.

    It is deliberately not read from the repository under review: a prompt
    supplied by the code being judged could ask the reviewer to report nothing,
    and the verdict would look exactly like a clean change.
    """
    return Path(__file__).parent / "prompts" / "reviewer.md"


@dataclass(frozen=True, slots=True)
class ReviewRequest:
    repo: Path
    base: str | None = None
    samples: int | None = None
    profile: str = DEFAULT_PROFILE
    run_id: str | None = None
    prompt: Path | None = None
    context_urls: tuple[str, ...] = ()
    allow_large_prompt: bool = False
    max_prompt_bytes: int = PROMPT_LIMIT
    context_depth: int = 3
    time_budget: int = 0
    reasoning: str | None = None
    stream: bool = False
    idle_timeout: int = 120


@dataclass(frozen=True, slots=True)
class Report:
    """Everything the caller needs to act on, and where the evidence is."""

    run_dir: Path
    base: str
    head: str
    digest: str
    result: Result
    samples: tuple[SampleResult, ...]
    prompt: Path | None = None
    ignored: bool = True
    skipped: tuple[Skipped, ...] = ()
    diff_sha256: str = ""
    context_digest: str = ""

    @property
    def verdict(self) -> Verdict:
        return self.result.verdict

    @property
    def findings(self) -> tuple[Finding, ...]:
        return self.result.findings

    @property
    def exit_code(self) -> int:
        return self.result.exit_code


@dataclass(frozen=True, slots=True)
class Unit:
    """One prompt-sized slice of the change."""

    id: str
    files: tuple[str, ...]
    ranges: tuple[tuple[str, int, int], ...]
    patch: str
    prompt: str
    depth: int
    bytes: int
    context_digest: str


@dataclass(frozen=True, slots=True)
class Fitted:
    prompt: str
    context: Context
    depth: int
    bytes: int


def _prompt_for(template: str, base: str, patch: str, root: Path, depth: int,
                references: tuple[Reference, ...]) -> Fitted:
    context = build_context(patch, _reader(root), python_files(root),
                            max_depth=depth - 1)
    text = context.text
    if references:
        text = f"{text}\n\n{_reference_text(references)}"
    prompt = render(template, base=base, diff=patch, context=text)
    return Fitted(prompt, context, depth, len(prompt.encode("utf-8")))


def _fit(template: str, base: str, patch: str, root: Path, depth: int,
         references: tuple[Reference, ...], limit: int) -> Fitted | None:
    """The deepest context depth whose prompt fits, or None if even depth 0 does not."""
    for candidate in range(depth, -1, -1):
        fitted = _prompt_for(template, base, patch, root, candidate, references)
        if fitted.bytes <= limit:
            return fitted
    return None


def _build_units(template: str, base: str, patch: str, root: Path,
                 request: ReviewRequest, references: tuple[Reference, ...]) -> list[Unit]:
    """File first, then hunks; deterministic, and each unit fits the budget."""
    limit = request.max_prompt_bytes
    units: list[Unit] = []

    def add(files: tuple[str, ...], ranges: tuple[tuple[str, int, int], ...],
            text: str, fitted: Fitted) -> None:
        units.append(Unit(f"unit-{len(units) + 1:03d}", files, ranges, text,
                          fitted.prompt, fitted.depth, fitted.bytes,
                          fitted.context.digest))

    for section in file_sections(patch):
        hunks = hunk_sections(section.text)
        if not hunks:
            continue
        ranges = tuple((section.path, *hunk_range(hunk)) for hunk in hunks)
        fitted = _fit(template, base, section.text, root, request.context_depth,
                      references, limit)
        if fitted is not None:
            add((section.path,), ranges, section.text, fitted)
            continue
        for hunk in hunks:
            fitted = _fit(template, base, hunk, root, request.context_depth,
                          references, limit)
            if fitted is None:
                smallest = _prompt_for(template, base, hunk, root, 0, references)
                raise PromptTooLarge(smallest.bytes, limit, unit=section.path)
            add((section.path,), ((section.path, *hunk_range(hunk)),), hunk, fitted)
    if not units:
        raise ReviewError("the change has no reviewable file section")
    return units


def _belongs(finding: Finding, unit: Unit) -> bool:
    try:
        path, raw = finding.location.rsplit(":", 1)
        line = int(raw)
    except ValueError:
        return False
    if path not in unit.files:
        return False
    if not unit.ranges:
        return True
    return any(file == path and start <= line <= end for file, start, end in unit.ranges)


def _unit_verdict(findings: Sequence[Finding], ok: bool) -> str:
    if not ok:
        return "incomplete"
    if any(finding.blocks and finding.state is State.PROVEN for finding in findings):
        return "fail"
    if any(finding.blocks and finding.state in OPEN_STATES for finding in findings):
        return "incomplete"
    return "pass"


def _blocking_key(sample: SampleResult) -> frozenset[tuple[str, str, int, str]] | None:
    """What a sample says would block, independent of wording or proof order."""
    if sample.output is None:
        return None
    return frozenset((item.dimension, item.file, item.line, item.severity)
                     for item in sample.output.findings
                     if blocks(item.dimension, item.severity))


def _samples(prompt: str, runner: Runner,
             requested: int | None) -> tuple[tuple[SampleResult, ...], int, bool | None]:
    """Fixed N, or auto: one clean sample, two to confirm a finding, three to break a tie."""
    if requested is not None:
        fixed = tuple(run_sample(prompt, runner, index=index)
                      for index in range(1, requested + 1))
        return fixed, requested, None

    first = run_sample(prompt, runner, index=1)
    if first.output is None:
        # The retry inside `run_sample` already covered a flaky reviewer; asking
        # a missing binary two more times only multiplies the same error.
        return (first,), 1, None
    if not first.output.findings:
        return (first,), 1, True

    results = [first, run_sample(prompt, runner, index=2)]
    agreed: bool | None = (results[1].output is not None
                           and _blocking_key(first) == _blocking_key(results[1]))
    if not agreed and len(results) < AUTO_MAX:
        results.append(run_sample(prompt, runner, index=3))
        keys = [key for key in (_blocking_key(sample) for sample in results) if key is not None]
        agreed = len(set(keys)) == 1 if keys else None
    return tuple(results), len(results), agreed


def _reader(root: Path) -> Callable[[str], str | None]:
    """Read a repository-relative file, refusing anything that resolves outside it."""
    base = root.resolve()

    def read(rel: str) -> str | None:
        try:
            target = (base / rel).resolve()
            if not target.is_relative_to(base):
                return None
            return target.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return None

    return read


def _reference_text(references: tuple[Reference, ...]) -> str:
    if not references:
        return ""
    blocks = ["## Reference (fetched by the caller; context, not evidence)"]
    blocks.extend(f"### {item.url} ({item.sha256})\n{item.text}" for item in references)
    return "\n\n".join(blocks)


def _write_verdict(run_dir: Path, request: ReviewRequest, base: str, head: str,
                   digest: str, prompt: Path, ignored: bool,
                   samples: tuple[SampleResult, ...], result: Result, *,
                   worktree: bool, diff_sha256: str,
                   skipped: tuple[Skipped, ...], context: Context,
                   references: tuple[Reference, ...],
                   samples_run: int, agreement: bool | None,
                   prompt_bytes: int, prompt_limit: int,
                   prompt_acknowledged: bool,
                   sliced: bool = False,
                   time_budget: int = 0,
                   units: Sequence[dict[str, object]] = ()) -> None:
    payload = {
        "run": run_dir.name,
        "base": base,
        "head": head,
        "worktree": worktree,
        "diff_sha256": diff_sha256,
        "digest": digest,
        "prompt": str(prompt),
        "prompt_bytes": prompt_bytes,
        "prompt_limit": prompt_limit,
        "prompt_acknowledged": prompt_acknowledged,
        "sliced": sliced,
        "time_budget": time_budget,
        "units": list(units),
        "state_dir_ignored": ignored,
        "profile": request.profile,
        "reasoning": request.reasoning or "profile-default",
        "transport": "stream" if request.stream else "plain",
        "idle_timeout": request.idle_timeout,
        "samples_requested": request.samples if request.samples is not None else "auto",
        "samples_run": samples_run,
        "agreement": agreement,
        "samples": [
            {"index": sample.index, "ok": sample.ok, "attempts": sample.attempts,
             "error": sample.error, "findings": len(sample.output.findings)
             if sample.output is not None else 0}
            for sample in samples
        ],
        "skipped": [{"path": item.path, "reason": item.reason} for item in skipped],
        "context_digest": context.digest,
        "context_depth": request.context_depth,
        "context": [{"file": span.file, "start": span.start, "end": span.end,
                     "name": span.name, "reason": span.reason} for span in context.spans],
        "unresolved": list(context.unresolved),
        "references": [{"url": item.url, "sha256": item.sha256, "bytes": len(item.text.encode("utf-8"))}
                       for item in references],
        "verdict": result.verdict.value,
        "exit_code": result.exit_code,
        "reason": result.reason,
        "findings": [
            {"id": finding.id, "dimension": finding.dimension,
             "severity": finding.severity, "state": finding.state.value,
             "location": finding.location, "claim": finding.claim,
             "detail": finding.detail}
            for finding in result.findings
        ],
    }
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "verdict.json").write_text(
        json.dumps(payload, indent=2) + "\n", encoding="utf-8", newline="\n")


def review(request: ReviewRequest, runner: Runner) -> Report:
    """Run one review and write every artefact under `.council/runs/<id>/`.

    A prompt over `request.max_prompt_bytes` is not sent. The call refuses with
    `PromptTooLarge` before the reviewer is asked and before any run directory
    exists; the caller either narrows the change, raises the budget, or sets
    `allow_large_prompt`. The decision belongs to a person (or to an explicit
    flag), never to the tool guessing.
    """
    if request.samples is not None and request.samples < 1:
        raise ReviewError("samples must be at least 1")

    root = repo_root(request.repo)
    base = resolve_base(root, request.base)
    head = output(root, "rev-parse", "HEAD").strip()
    change = diff(root, base)
    patch = change.patch
    diff_sha256 = hashlib.sha256(patch.encode("utf-8")).hexdigest()
    try:
        references = tuple(fetch(url) for url in request.context_urls)
    except FetchError as exc:
        raise ReviewError(str(exc)) from exc

    prompt_file = request.prompt if request.prompt is not None else default_prompt()
    if not prompt_file.exists():
        raise ReviewError(f"no reviewer prompt at {prompt_file}: a review needs an instrument")
    template = prompt_file.read_text(encoding="utf-8")
    digest = instrument_digest(template, profile=request.profile,
                               reasoning=request.reasoning)

    run_id = (request.run_id if request.run_id is not None
              else datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S"))
    if not run_id.strip():
        raise ReviewError("--run-id must not be empty")
    try:
        directory = run_path(root, run_id)
    except ValueError as exc:
        raise ReviewError(str(exc)) from exc
    if directory.is_symlink() or directory.exists():
        raise ReviewError(f"run {run_id!r} already exists at {directory}")

    limit = request.max_prompt_bytes
    acknowledged = request.allow_large_prompt
    full_context = build_context(patch, _reader(root), python_files(root),
                                 max_depth=request.context_depth - 1)
    prompt_context = full_context.text
    if references:
        prompt_context = f"{prompt_context}\n\n{_reference_text(references)}"
    prompt = render(template, base=base, diff=patch, context=prompt_context)
    prompt_bytes = len(prompt.encode("utf-8"))
    sliced = prompt_bytes > limit and not acknowledged

    config = load_config(root / CONFIG_NAME)
    proofs = ProofContext(repo=root, allow=config.allow, diff=patch,
                          timeout=config.timeout, sandbox=config.sandbox)
    units_payload: list[dict[str, object]] = []

    if not sliced:
        samples, samples_run, agreement = _samples(prompt, runner, request.samples)
        for sample in samples:
            write_sample(directory, sample)
        merged = merge([sample.output.findings if sample.output is not None else ()
                        for sample in samples])
        adjudication = adjudicate(
            merged, proofs,
            failed_samples=[sample.index for sample in samples if not sample.ok])
        result = verdict(adjudication)
        reported_context = full_context
    else:
        units = _build_units(template, base, patch, root, request, references)
        runs: list[tuple[Unit, tuple[SampleResult, ...], int, bool | None, bool]] = []
        raw: list[RawFinding] = []
        skipped_by_budget: set[str] = set()
        started = time.monotonic()
        for unit in units:
            if request.time_budget and time.monotonic() - started >= request.time_budget:
                # The budget stops starting units; the one in flight was allowed
                # to finish. A unit never asked is unreviewed, not clean.
                skipped_by_budget.add(unit.id)
                runs.append((unit, (), 0, None, False))
                continue
            unit_samples, unit_run, unit_agreement = _samples(
                unit.prompt, runner, request.samples)
            for sample in unit_samples:
                write_sample(directory / "units" / unit.id, sample)
            ok = all(sample.ok for sample in unit_samples)
            runs.append((unit, unit_samples, unit_run, unit_agreement, ok))
            for sample in unit_samples:
                if sample.output is not None:
                    raw.extend(sample.output.findings)
        merged = merge([raw])
        adjudication = adjudicate(merged, proofs)
        result = verdict(adjudication)
        unreviewed = [unit.id for unit, _, _, _, ok in runs if not ok]
        if unreviewed:
            silent = [unit_id for unit_id in unreviewed if unit_id not in skipped_by_budget]
            late = [unit_id for unit_id in unreviewed if unit_id in skipped_by_budget]
            reasons = []
            if silent:
                reasons.append(f"unit(s) {', '.join(silent)} returned nothing usable")
            if late:
                reasons.append(f"unit(s) {', '.join(late)} were not reviewed within "
                               f"the {request.time_budget}s time budget")
            note = "; ".join(reasons)
            if result.verdict is Verdict.PASS:
                result = Result(
                    Verdict.INCOMPLETE,
                    note + ": the review is missing evidence",
                    result.findings,
                )
            else:
                # FAIL and INCOMPLETE both outrank a missing unit, but the reason
                # must still say what was never looked at.
                result = Result(result.verdict, f"{result.reason}; {note}", result.findings)
        for unit, unit_samples, unit_run, unit_agreement, ok in runs:
            mine = [finding for finding in result.findings if _belongs(finding, unit)]
            units_payload.append({
                "id": unit.id,
                "files": list(unit.files),
                "ranges": [{"file": file, "start": start, "end": end}
                           for file, start, end in unit.ranges],
                "diff_sha256": hashlib.sha256(unit.patch.encode("utf-8")).hexdigest(),
                "context_digest": unit.context_digest,
                "context_depth": unit.depth,
                "prompt_bytes": unit.bytes,
                "samples_run": unit_run,
                "agreement": unit_agreement,
                "ok": ok,
                "error": ("time budget exhausted"
                          if unit.id in skipped_by_budget else None),
                "findings": len(mine),
                "verdict": _unit_verdict(mine, ok),
            })
        samples = ()
        samples_run = sum(run[2] for run in runs)
        agreement = None
        reported_context = Context((), (), "", "")

    ignored = state_dir_ignored(root)
    _write_verdict(directory, request, base, head, digest, prompt_file, ignored,
                   samples, result, worktree=True, diff_sha256=diff_sha256,
                   skipped=change.skipped, context=reported_context,
                   references=references,
                   samples_run=samples_run, agreement=agreement,
                   prompt_bytes=prompt_bytes, prompt_limit=limit,
                   prompt_acknowledged=acknowledged,
                   sliced=sliced, time_budget=request.time_budget,
                   units=units_payload)
    return Report(directory, base, head, digest, result, samples, prompt_file, ignored,
                  change.skipped, diff_sha256, reported_context.digest)
