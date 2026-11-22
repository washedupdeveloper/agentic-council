"""One review: request in, written run out. The runner is a parameter."""

# ruff: noqa: I001, PLC0414 - explicit aliases are the public re-export surface

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from .adjudicate import adjudicate, verdict
from .domain.adjudication import missing_evidence
from .domain.baseline import GateResult, apply_baseline
from .domain.scope import ScopeIgnored
from .domain.findings import Finding
from .domain.merge import merge
from .paths import run_dir as run_path, validate_run_id
from .planning import (Plan as Plan, Prepared as Prepared,
                       PromptTooLarge as PromptTooLarge, Unit as Unit,
                       build_units as _build_units)
from .prepare import default_prompt as default_prompt, prepare as _prepare
from .request import (DEFAULT_PROFILE as DEFAULT_PROFILE,
                      PROMPT_LIMIT as PROMPT_LIMIT,
                      ReviewRequest as ReviewRequest)
from .runstore import (UnitRun, VerdictDocument, claim as _claim,
                       discard_empty as _discard_empty, unit_payload,
                       write_sample as _write_sample, write_verdict)
from .sampling import (samples as _samples, unit_verdict as _unit_verdict)
from .proofs import ProofContext
from .repo import ReviewError, Skipped, state_dir_ignored
from .sample import Runner, SampleResult
from .domain.schema import RawFinding
from .domain.verdict import Result, Verdict


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


def plan(request: ReviewRequest) -> Plan:
    """The units, prompt sizes and skipped files a review would use. No model call."""
    prepared = _prepare(request)
    units: tuple[Unit, ...] = ()
    if prepared.sliced:
        units = tuple(_build_units(prepared.template, prepared.base, prepared.patch,
                                   prepared.root, request, prepared.references,
                                   prepared.rules_text))
    windows = sum(1 for unit in units if unit.window)
    # A clean unit is confirmed by a second sample; a finding may take a third.
    # The plan states the span rather than a single number.
    low = len(units) * (request.samples if request.samples is not None else 2)
    high = len(units) * (request.samples if request.samples is not None else 3)
    return Plan(prepared.base, prepared.head, prepared.prompt_bytes,
                request.max_prompt_bytes, prepared.sliced, units,
                prepared.skipped, request.context_depth, prepared.scope_ignored,
                request.include, request.exclude, windows, (low, high),
                prepared.rules)


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
    units = _build_units(template, base, patch, root, request, references,
                         prepared.rules_text) if sliced else []
    # The whole change is the degenerate case: one unit, written at the run root.
    # Keeping it as a unit means the evidence loop below has one shape, while the
    # on-disk layout stays compatible with the whole-change format.
    whole = Unit("", (), (), patch, prompt, request.context_depth,
                 len(prompt.encode("utf-8")), full_context.digest)
    run_units = units if sliced else [whole]
    _claim(directory, run_id)
    units_payload: list[dict[str, object]] = []

    try:
        runs: list[UnitRun] = []
        samples: tuple[SampleResult, ...] = ()
        raw: list[RawFinding] = []
        raw_by_unit: dict[str, list[RawFinding]] = {}
        #: One list per sample, in run order, and the file each was written to.
        #: The merge keeps the trail so a finding can name its own evidence.
        per_sample: list[list[RawFinding]] = []
        evidence_labels: list[str] = []
        started = time.monotonic()
        for unit in run_units:
            if sliced and request.time_budget and time.monotonic() - started >= request.time_budget:
                # The budget stops starting units; the one in flight was allowed
                # to finish. A unit never asked is unreviewed, not clean.
                runs.append(UnitRun(unit, error="time budget exhausted"))
                continue
            unit_samples, unit_run, unit_agreement = _samples(
                unit.prompt, runner, request.samples)
            sample_dir = directory / "units" / unit.id if sliced else directory
            for sample in unit_samples:
                _write_sample(sample_dir, sample)
            ok = all(sample.ok for sample in unit_samples)
            runs.append(UnitRun(unit, unit_samples, unit_run, unit_agreement, ok))
            for sample in unit_samples:
                per_sample.append(list(sample.output.findings)
                                  if sample.output is not None else [])
                evidence_labels.append(
                    f"units/{unit.id}/sample-{sample.index}.json" if sliced
                    else f"sample-{sample.index}.json")
                if sample.output is not None:
                    raw.extend(sample.output.findings)
                    raw_by_unit.setdefault(unit.id, []).extend(sample.output.findings)
        merged = merge(per_sample, labels=evidence_labels)
        if sliced:
            adjudication = adjudicate(merged, proofs)
        else:
            adjudication = adjudicate(
                merged, proofs,
                failed_samples=[sample.index for sample in runs[0].samples if not sample.ok])
        result = verdict(adjudication,
                        executed_only=request.require_executed_proofs)
        if sliced:
            unreviewed = [run for run in runs if not run.ok]
            silent = [run.unit.id for run in unreviewed if run.error is None]
            late = [run.unit.id for run in unreviewed if run.error is not None]
            result = missing_evidence(result, silent=silent, late=late,
                                      budget=request.time_budget)
            for run in runs:
                places = {(item.dimension, item.file, item.line)
                          for item in raw_by_unit.get(run.unit.id, ())}
                mine = [finding for finding in result.findings
                        if (finding.dimension, finding.file, finding.line) in places]
                units_payload.append(
                    unit_payload(run, mine, _unit_verdict(mine, run.ok)))
            samples = ()
            samples_run = sum(run.samples_run for run in runs)
            agreement = None
        else:
            samples, samples_run, agreement = runs[0].samples, runs[0].samples_run, runs[0].agreement
        incomplete = any(not run.ok for run in runs)
        reported_context = full_context

        ignored = True if request.state_dir is not None else state_dir_ignored(root)
        gate = None
        if prepared.baseline is not None:
            gate = apply_baseline(result, prepared.baseline,
                                  today=datetime.now(UTC).date(),
                                  strict=request.baseline_strict,
                                  missing_evidence=incomplete)
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
