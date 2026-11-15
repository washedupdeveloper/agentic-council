"""The on-disk run: exclusive claim, sample files and the verdict document.

This is the only module that knows the `verdict.json` shape. The review loop
constructs one `VerdictDocument`; adding a payload key is a change here, not in
the orchestration.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from .context import Context
from .domain.baseline import GateResult
from .planning import Prepared
from .repo import ReviewError
from .request import ReviewRequest
from .sample import SampleResult
from .sample import write_sample as _write_sample_file
from .verdict import Result


@dataclass(frozen=True, slots=True)
class VerdictDocument:
    run_dir: Path
    request: ReviewRequest
    prepared: Prepared
    result: Result
    samples: tuple[SampleResult, ...]
    samples_run: int
    agreement: bool | None
    units: Sequence[dict[str, object]]
    reported_context: Context
    ignored: bool
    baseline_source: str = ""
    gate: GateResult | None = None


def claim(directory: Path, run_id: str) -> None:
    """Create the run directory exclusively: a second run cannot share it."""
    try:
        directory.mkdir(parents=True, exist_ok=False)
    except FileExistsError as exc:
        raise ReviewError(f"run {run_id!r} already exists at {directory}") from exc
    except OSError as exc:
        raise ReviewError(f"cannot create the run directory {directory}: {exc}") from exc


def discard_empty(directory: Path) -> None:
    """Remove the claim if the run failed before writing any evidence."""
    try:
        if directory.is_dir() and not any(directory.iterdir()):
            directory.rmdir()
    except OSError:
        pass


def write_sample(directory: Path, sample: SampleResult) -> None:
    try:
        _write_sample_file(directory, sample)
    except (OSError, ValueError) as exc:
        raise ReviewError(f"cannot write a sample under {directory}: {exc}") from exc


def write_verdict(document: VerdictDocument) -> None:
    """Serialize the one document the rest of the tool reads."""
    request = document.request
    prepared = document.prepared
    result = document.result
    effective = document.gate or result
    context = document.reported_context
    payload = {
        "run": document.run_dir.name,
        "base": prepared.base,
        "head": prepared.head,
        "worktree": not request.staged,
        "staged": request.staged,
        "scope": {"include": list(request.include), "exclude": list(request.exclude)},
        "diff_sha256": prepared.diff_sha256,
        "digest": prepared.digest,
        "prompt": str(prepared.prompt_file),
        "prompt_bytes": prepared.prompt_bytes,
        "prompt_limit": request.max_prompt_bytes,
        "prompt_acknowledged": request.allow_large_prompt,
        "sliced": prepared.sliced,
        "time_budget": request.time_budget,
        "units": list(document.units),
        "state_dir_ignored": document.ignored,
        "profile": request.profile,
        "reasoning": request.reasoning or "profile-default",
        "transport": "stream" if request.stream else "plain",
        "idle_timeout": request.idle_timeout,
        "reviewer_sandbox": request.sandbox,
        "ephemeral": request.state_dir is not None,
        "pull_request": None if request.pull_request is None else {
            "number": request.pull_request.number,
            "url": request.pull_request.url,
            "title": request.pull_request.title,
            "base": request.pull_request.base,
            "head": request.pull_request.head,
        },
        "samples_requested": request.samples if request.samples is not None else "auto",
        "samples_run": document.samples_run,
        "agreement": document.agreement,
        "samples": [
            {"index": sample.index, "ok": sample.ok, "attempts": sample.attempts,
             "error": sample.error, "findings": len(sample.output.findings)
             if sample.output is not None else 0}
            for sample in document.samples
        ],
        "skipped": [{"path": item.path, "reason": item.reason} for item in prepared.skipped],
        "scope_ignored": [
            {"path": item.path, "reason": item.reason, "pattern": item.pattern}
            for item in prepared.scope_ignored
        ],
        "context_digest": context.digest,
        "context_depth": request.context_depth,
        "context": [{"file": span.file, "start": span.start, "end": span.end,
                     "name": span.name, "reason": span.reason} for span in context.spans],
        "unresolved": list(context.unresolved),
        "references": [{"url": item.url, "sha256": item.sha256,
                        "bytes": len(item.text.encode("utf-8"))}
                       for item in prepared.references],
        "verdict": effective.verdict.value,
        "exit_code": effective.exit_code,
        "reason": effective.reason,
        "evidence_verdict": result.verdict.value,
        "baseline": None if prepared.baseline is None else {
            "source": document.baseline_source,
            "entries": len(prepared.baseline.entries),
            "suppressed": list(document.gate.suppressed) if document.gate is not None else [],
            "expired": list(document.gate.expired) if document.gate is not None else [],
            "stale": list(document.gate.stale) if document.gate is not None else [],
        },
        "findings": [
            {"id": finding.id, "dimension": finding.dimension,
             "severity": finding.severity, "state": finding.state.value,
             "location": finding.location, "claim": finding.claim,
             "detail": finding.detail, "proof": finding.proof}
            for finding in result.findings
        ],
    }
    try:
        document.run_dir.mkdir(parents=True, exist_ok=True)
        (document.run_dir / "verdict.json").write_text(
            json.dumps(payload, indent=2) + "\n", encoding="utf-8", newline="\n")
    except (OSError, ValueError) as exc:
        raise ReviewError(
            f"cannot write {document.run_dir / 'verdict.json'}: {exc}") from exc
