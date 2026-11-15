"""One review: request in, written run out. The runner is a parameter."""

# ruff: noqa: I001, PLC0414 - explicit aliases are the public re-export surface

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from .adjudicate import adjudicate, verdict
from .base import resolve_base
from .baseline import load as load_baseline, load_at as load_baseline_at
from .changes import file_sections
from .config import CONFIG_NAME, load as load_config
from .domain.baseline import Baseline, GateResult, apply_baseline
from .domain.scope import Scope, ScopeError, ScopeIgnored
from .findings import Finding
from .merge import merge
from .paths import run_dir as run_path, validate_run_id
from .planning import (Plan as Plan, Prepared as Prepared,
                       PromptTooLarge as PromptTooLarge, Unit as Unit,
                       build_units as _build_units,
                       prompt_for as _prompt_for)
from .request import (DEFAULT_PROFILE as DEFAULT_PROFILE,
                      PROMPT_LIMIT as PROMPT_LIMIT,
                      ReviewRequest as ReviewRequest)
from .runstore import (VerdictDocument, claim as _claim,
                       discard_empty as _discard_empty,
                       write_sample as _write_sample, write_verdict)
from .sampling import (samples as _samples, unit_verdict as _unit_verdict)
from .prompt import PromptError, instrument_digest
from .proofs import ProofContext
from .reference import FetchError, fetch
from .repo import (ReviewError, Skipped, diff, output,
                   root as repo_root, state_dir_ignored)
from .sample import Runner, SampleResult
from .schema import RawFinding
from .verdict import Result, Verdict


def default_prompt() -> Path:
    """The instrument ships with the tool.

    It is deliberately not read from the repository under review: a prompt
    supplied by the code being judged could ask the reviewer to report nothing,
    and the verdict would look exactly like a clean change.
    """
    return Path(__file__).parent / "prompts" / "reviewer.md"


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
    scope_ignored: tuple[ScopeIgnored, ...] = ()
    diff_sha256: str = ""
    context_digest: str = ""
    gate: GateResult | None = None

    @property
    def verdict(self) -> Verdict:
        return self.gate.verdict if self.gate is not None else self.result.verdict

    @property
    def findings(self) -> tuple[Finding, ...]:
        return self.result.findings

    @property
    def exit_code(self) -> int:
        return self.gate.exit_code if self.gate is not None else self.result.exit_code

    @property
    def reason(self) -> str:
        return self.gate.reason if self.gate is not None else self.result.reason

    @property
    def effective(self) -> Result:
        """The post-gate result: suppressed findings are no longer present."""
        if self.gate is None or not self.gate.suppressed:
            return self.result
        suppressed = set(self.gate.suppressed)
        return Result(self.gate.verdict, self.gate.reason,
                      tuple(item for item in self.result.findings
                            if item.id not in suppressed))


def _load_baseline(request: ReviewRequest, root: Path, base: str) -> Baseline | None:
    """Load the policy file before the expensive work; CI reads the base blob."""
    if request.baseline is None:
        return None
    if request.baseline_from_base:
        return load_baseline_at(root, base, str(request.baseline))
    path = request.baseline if request.baseline.is_absolute() else root / request.baseline
    return load_baseline(path)


def _baseline_changed(request: ReviewRequest, patch: str) -> bool:
    """Whether the committed baseline is itself part of the reviewed diff."""
    if request.baseline is None or not request.baseline_from_base:
        return False
    rel = str(request.baseline).replace("\\", "/")
    while rel.startswith("./"):
        rel = rel[2:]
    return any(section.path == rel for section in file_sections(patch))


def _prepare(request: ReviewRequest) -> Prepared:
    """Resolve the change and build the prompt, writing nothing.

    This is an application step, not a pure decision: it reads git, the
    repository configuration, the baseline, the prompt and any caller-supplied
    references. It loads the cheap policy inputs and validates the change and
    prompt before fetching references, so a cheap failure never pays for a
    network call.
    """
    root = repo_root(request.repo)
    try:
        request.validate()
    except ValueError as exc:
        raise ReviewError(str(exc)) from exc
    config = load_config(root / CONFIG_NAME)
    try:
        scope = Scope.create(request.include, request.exclude)
    except ScopeError as exc:
        raise ReviewError(str(exc)) from exc
    base = resolve_base(root, request.base)
    baseline = _load_baseline(request, root, base)
    head = output(root, "rev-parse", "HEAD").strip()
    change = diff(root, base, staged=request.staged)
    if _baseline_changed(request, change.patch) and not request.allow_baseline_change:
        raise ReviewError(
            "the baseline file is changed in this diff; refusing to use a "
            "baseline the change itself can edit (use --allow-baseline-change "
            "only for a deliberate maintenance change)")
    # `git` decodes with surrogateescape so a non-UTF-8 path stays readable; a
    # non-UTF-8 *content* byte becomes a lone surrogate, which cannot be encoded
    # into the prompt. Replace those bytes once, here, so the prompt is valid.
    patch = change.patch.encode("utf-8", "surrogateescape").decode("utf-8", "replace")
    if scope.includes or scope.excludes:
        patch, scope_ignored = scope.filter_patch(patch)
    else:
        scope_ignored = ()
    diff_sha256 = hashlib.sha256(patch.encode("utf-8")).hexdigest()

    if not patch.strip():
        if scope_ignored:
            names = ", ".join(item.path for item in scope_ignored[:5])
            more = f", +{len(scope_ignored) - 5} more" if len(scope_ignored) > 5 else ""
            raise ReviewError(
                f"the change has no reviewable text in scope; ignored "
                f"{len(scope_ignored)} file(s): {names}{more}")
        if change.skipped:
            names = ", ".join(item.path for item in change.skipped[:5])
            more = f", +{len(change.skipped) - 5} more" if len(change.skipped) > 5 else ""
            raise ReviewError(
                f"the change has no reviewable text; skipped {len(change.skipped)} "
                f"file(s): {names}{more}")
        raise ReviewError("the change is empty: base and head are the same")

    prompt_file = request.prompt if request.prompt is not None else default_prompt()
    try:
        if not prompt_file.is_file():
            raise ReviewError(f"no reviewer prompt at {prompt_file}: a review needs an instrument")
        template = prompt_file.read_text(encoding="utf-8")
    except ReviewError:
        raise
    except (OSError, UnicodeDecodeError) as exc:
        raise ReviewError(f"cannot read the reviewer prompt at {prompt_file}: {exc}") from exc
    digest = instrument_digest(template, profile=request.profile,
                               reasoning=request.reasoning)

    try:
        references = tuple(fetch(url) for url in request.context_urls)
    except FetchError as exc:
        raise ReviewError(str(exc)) from exc

    try:
        fitted = _prompt_for(template, base, patch, root, request.context_depth,
                             references)
    except PromptError as exc:
        raise ReviewError(f"the reviewer prompt is not usable: {exc}") from exc
    full_context = fitted.context
    prompt = fitted.prompt
    prompt_bytes = fitted.bytes
    sliced = prompt_bytes > request.max_prompt_bytes and not request.allow_large_prompt
    return Prepared(root, config, baseline, base, head, patch, change.skipped,
                    scope_ignored, references, prompt_file, template, digest, prompt,
                    prompt_bytes, sliced, full_context, diff_sha256)


def plan(request: ReviewRequest) -> Plan:
    """The units, prompt sizes and skipped files a review would use. No model call."""
    prepared = _prepare(request)
    units: tuple[Unit, ...] = ()
    if prepared.sliced:
        units = tuple(_build_units(prepared.template, prepared.base, prepared.patch,
                                   prepared.root, request, prepared.references))
    return Plan(prepared.base, prepared.head, prepared.prompt_bytes,
                request.max_prompt_bytes, prepared.sliced, units,
                prepared.skipped, request.context_depth, prepared.scope_ignored,
                request.include, request.exclude)


def review(request: ReviewRequest, runner: Runner) -> Report:
    """Run one review and write every artefact under `.council/runs/<id>/`.

    A prompt over `request.max_prompt_bytes` is not sent. The call refuses with
    `PromptTooLarge` before the reviewer is asked and before any run directory
    exists; the caller either narrows the change, raises the budget, or sets
    `allow_large_prompt`. The decision belongs to a person (or to an explicit
    flag), never to the tool guessing.
    """
    try:
        request.validate()
    except ValueError as exc:
        raise ReviewError(str(exc)) from exc

    prepared = _prepare(request)
    try:
        run_id = validate_run_id(
            request.run_id if request.run_id is not None
            else datetime.now(UTC).strftime("%Y%m%d-%H%M%S"))
    except ValueError as exc:
        raise ReviewError(str(exc)) from exc
    root = prepared.root
    base = prepared.base
    head = prepared.head
    patch = prepared.patch
    diff_sha256 = prepared.diff_sha256
    references = prepared.references
    prompt_file = prepared.prompt_file
    template = prepared.template
    digest = prepared.digest
    full_context = prepared.full_context
    prompt = prepared.prompt
    sliced = prepared.sliced

    try:
        directory = (request.state_dir if request.state_dir is not None
                     else run_path(root, run_id))
    except ValueError as exc:
        raise ReviewError(str(exc)) from exc
    if request.state_dir is not None:
        try:
            if directory.is_symlink():
                raise ReviewError(f"{directory} is a symlink: a run must not write outside its state directory")
            if directory.exists() and not directory.is_dir():
                raise ReviewError(f"{directory} exists and is not a directory")
        except ReviewError:
            raise
        except (OSError, ValueError) as exc:
            raise ReviewError(f"cannot use the state directory {directory}: {exc}") from exc

    config = prepared.config
    proofs = ProofContext(repo=root, allow=config.allow, diff=patch,
                          timeout=config.timeout, sandbox=config.sandbox)
    units = _build_units(template, base, patch, root, request, references) if sliced else []
    _claim(directory, run_id)
    units_payload: list[dict[str, object]] = []
    missing_evidence = False

    try:
        if not sliced:
            samples, samples_run, agreement = _samples(prompt, runner, request.samples)
            missing_evidence = any(not sample.ok for sample in samples)
            for sample in samples:
                _write_sample(directory, sample)
            merged = merge([sample.output.findings if sample.output is not None else ()
                            for sample in samples])
            adjudication = adjudicate(
                merged, proofs,
                failed_samples=[sample.index for sample in samples if not sample.ok])
            result = verdict(adjudication)
            reported_context = full_context
        else:
            runs: list[tuple[Unit, tuple[SampleResult, ...], int, bool | None, bool]] = []
            raw: list[RawFinding] = []
            raw_by_unit: dict[str, list[RawFinding]] = {}
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
                    _write_sample(directory / "units" / unit.id, sample)
                ok = all(sample.ok for sample in unit_samples)
                runs.append((unit, unit_samples, unit_run, unit_agreement, ok))
                for sample in unit_samples:
                    if sample.output is not None:
                        raw.extend(sample.output.findings)
                        raw_by_unit.setdefault(unit.id, []).extend(sample.output.findings)
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
                places = {(item.dimension, item.file, item.line)
                          for item in raw_by_unit.get(unit.id, ())}
                mine = [finding for finding in result.findings
                        if (finding.dimension, finding.file, finding.line) in places]
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
            missing_evidence = any(not run[4] for run in runs)
            reported_context = full_context

        ignored = True if request.state_dir is not None else state_dir_ignored(root)
        gate = None
        if prepared.baseline is not None:
            gate = apply_baseline(result, prepared.baseline,
                                  today=datetime.now(UTC).date(),
                                  strict=request.baseline_strict,
                                  missing_evidence=missing_evidence)
        baseline_source = ""
        if prepared.baseline is not None and request.baseline is not None:
            baseline_source = (f"{base}:{request.baseline}"
                               if request.baseline_from_base else str(request.baseline))
        write_verdict(VerdictDocument(
            run_dir=directory,
            request=request,
            prepared=prepared,
            result=result,
            samples=samples,
            samples_run=samples_run,
            agreement=agreement,
            units=units_payload,
            reported_context=reported_context,
            ignored=ignored,
            baseline_source=baseline_source,
            gate=gate,
        ))
    except BaseException:
        _discard_empty(directory)
        raise
    return Report(directory, base, head, digest, result, samples, prompt_file, ignored,
                  prepared.skipped, prepared.scope_ignored, diff_sha256,
                  reported_context.digest, gate=gate)
