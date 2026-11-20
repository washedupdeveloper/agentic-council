"""The on-disk run: exclusive claim, sample files and the verdict document.

This is the only module that knows the `verdict.json` shape. The review loop
constructs one `VerdictDocument`; adding a payload key is a change here, not in
the orchestration.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Sequence
from typing import TypeVar
from dataclasses import dataclass
from pathlib import Path

from .domain.context import Context
from .domain.baseline import GateResult
from .domain.findings import Finding
from .planning import Prepared, Unit
from .repo import ReviewError
from .request import ReviewRequest
from .sample import SampleResult
from .sample import write_sample as _write_sample_file
from .domain.verdict import Result


#: The `verdict.json` format. A consumer must refuse a format it does not know
#: rather than guess: the document is a contract, and a field added later is not
#: a field that was always absent.
VERDICT_FORMAT = 1

#: How many dropped paths the report names. The rest are counted, not hidden:
#: a review that lists ten thousand paths is a review nobody reads the end of.
SCOPE_REPORT_LIMIT = 200

T = TypeVar("T")


def bounded(items: Sequence[T], limit: int = SCOPE_REPORT_LIMIT) -> tuple[list[T], int]:
    """The first `limit` items, and how many were left out."""
    listed = list(items)
    return listed[:limit], max(0, len(listed) - limit)


@dataclass(frozen=True, slots=True)
class UnitRun:
    """One unit's turn through the loop: what was asked, and what came back.

    `error` is the reason a unit was not asked at all. It is distinct from a
    failed sample: one never reached a reviewer, the other reached one and got
    nothing usable, and the reason a run is INCOMPLETE has to say which.
    """

    unit: Unit
    samples: tuple[SampleResult, ...] = ()
    samples_run: int = 0
    agreement: bool | None = None
    ok: bool = False
    error: str | None = None


def unit_payload(run: UnitRun, findings: Sequence[Finding], verdict: str) -> dict[str, object]:
    """One `units[]` row. The document shape is decided here, not in the loop."""
    unit = run.unit
    return {
        "id": unit.id,
        "files": list(unit.files),
        "ranges": [{"file": file, "start": start, "end": end}
                   for file, start, end in unit.ranges],
        "diff_sha256": hashlib.sha256(unit.patch.encode("utf-8")).hexdigest(),
        "context_digest": unit.context_digest,
        "context_depth": unit.depth,
        "prompt_bytes": unit.bytes,
        "window": unit.window,
        "samples_run": run.samples_run,
        "agreement": run.agreement,
        "ok": run.ok,
        "error": run.error,
        "findings": len(findings),
        "verdict": verdict,
    }


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
    ignored, ignored_omitted = bounded(prepared.scope_ignored)
    payload = {
        "format": VERDICT_FORMAT,
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
        "window_large_files": request.window_large_files,
        "max_windows": request.max_windows,
        "require_executed_proofs": request.require_executed_proofs,
        "sliced": prepared.sliced,
        "time_budget": request.time_budget,
        "units": list(document.units),
        "state_dir_ignored": document.ignored,
        "agent": request.agent,
        "reviewer": prepared.reviewer or request.reviewer,
        "agent_config": prepared.agent_config,
        "agent_config_sha256": prepared.agent_config_sha256,
        "profile": request.profile,
        "profile_config": prepared.profile_config,
        "profile_config_sha256": prepared.profile_config_sha256,
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
            for item in ignored
        ],
        "scope_ignored_omitted": ignored_omitted,
        "context_digest": context.digest,
        "context_depth": request.context_depth,
        "context": [{"file": span.file, "start": span.start, "end": span.end,
                     "name": span.name, "reason": span.reason} for span in context.spans],
        "unresolved": list(context.unresolved),
        "rules": [{"glob": hit.glob, "doc": hit.doc, "paths": list(hit.paths),
                   "truncated": hit.truncated} for hit in prepared.rules],
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
             "detail": finding.detail, "proof": finding.proof,
             "proof_strength": "executed" if finding.executed else "static",
             "evidence": list(finding.evidence)}
            for finding in result.findings
        ],
    }
    document.run_dir.mkdir(parents=True, exist_ok=True)
    write_document(document.run_dir / "verdict.json", payload)


def write_document(target: Path, payload: dict[str, object]) -> None:
    """Publish one document whole: a reader sees the old file or the new one.

    A verdict written in place is a verdict a concurrent reader can catch half
    way through, and a CI job that reads invalid JSON learns the wrong thing
    about the change. The staging file lives in the same directory so the rename
    is one filesystem operation.
    """
    staging = target.with_name(f".{target.name}.tmp")
    try:
        with staging.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(payload, indent=2) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(staging, target)
    except (OSError, ValueError) as exc:
        try:
            staging.unlink()
        except OSError:
            pass
        raise ReviewError(f"cannot write {target}: {exc}") from exc
