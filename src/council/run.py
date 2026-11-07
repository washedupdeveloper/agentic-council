"""One review: request in, written run out. The runner is a parameter."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .adjudicate import adjudicate, verdict
from .base import resolve_base
from .config import CONFIG_NAME, load as load_config
from .context import Context, build as build_context
from .findings import Finding
from .merge import merge
from .paths import run_dir as run_path
from .prompt import instrument_digest, render
from .proofs import ProofContext
from .repo import (ReviewError, Skipped, diff, output, python_files,
                   root as repo_root, state_dir_ignored)
from .sample import Runner, SampleResult, run_sample, write_sample
from .verdict import Result, Verdict

DEFAULT_SAMPLES = 1
DEFAULT_PROFILE = "council-generalist"


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
    samples: int = DEFAULT_SAMPLES
    profile: str = DEFAULT_PROFILE
    run_id: str | None = None
    prompt: Path | None = None


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


def _write_verdict(run_dir: Path, request: ReviewRequest, base: str, head: str,
                   digest: str, prompt: Path, ignored: bool,
                   samples: tuple[SampleResult, ...], result: Result, *,
                   worktree: bool, diff_sha256: str,
                   skipped: tuple[Skipped, ...], context: Context) -> None:
    payload = {
        "run": run_dir.name,
        "base": base,
        "head": head,
        "worktree": worktree,
        "diff_sha256": diff_sha256,
        "digest": digest,
        "prompt": str(prompt),
        "state_dir_ignored": ignored,
        "profile": request.profile,
        "samples_requested": request.samples,
        "samples": [
            {"index": sample.index, "ok": sample.ok, "attempts": sample.attempts,
             "error": sample.error, "findings": len(sample.output.findings)
             if sample.output is not None else 0}
            for sample in samples
        ],
        "skipped": [{"path": item.path, "reason": item.reason} for item in skipped],
        "context_digest": context.digest,
        "context": [{"file": span.file, "start": span.start, "end": span.end,
                     "name": span.name, "reason": span.reason} for span in context.spans],
        "unresolved": list(context.unresolved),
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
    """Run one review and write every artefact under `.council/runs/<id>/`."""
    if request.samples < 1:
        raise ReviewError("samples must be at least 1")

    root = repo_root(request.repo)
    base = resolve_base(root, request.base)
    head = output(root, "rev-parse", "HEAD").strip()
    change = diff(root, base)
    patch = change.patch
    diff_sha256 = hashlib.sha256(patch.encode("utf-8")).hexdigest()
    context = build_context(patch, _reader(root), python_files(root))

    prompt_file = request.prompt if request.prompt is not None else default_prompt()
    if not prompt_file.exists():
        raise ReviewError(f"no reviewer prompt at {prompt_file}: a review needs an instrument")
    template = prompt_file.read_text(encoding="utf-8")
    digest = instrument_digest(template, profile=request.profile)

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

    prompt = render(template, base=base, diff=patch, context=context.text)
    samples = tuple(run_sample(prompt, runner, index=index)
                    for index in range(1, request.samples + 1))
    for sample in samples:
        write_sample(directory, sample)

    config = load_config(root / CONFIG_NAME)
    merged = merge([sample.output.findings if sample.output is not None else ()
                    for sample in samples])
    adjudication = adjudicate(
        merged,
        ProofContext(repo=root, allow=config.allow, diff=patch, timeout=config.timeout,
                     sandbox=config.sandbox),
        failed_samples=[sample.index for sample in samples if not sample.ok],
    )
    result = verdict(adjudication)
    ignored = state_dir_ignored(root)
    _write_verdict(directory, request, base, head, digest, prompt_file, ignored,
                   samples, result, worktree=True, diff_sha256=diff_sha256,
                   skipped=change.skipped, context=context)
    return Report(directory, base, head, digest, result, samples, prompt_file, ignored,
                  change.skipped, diff_sha256, context.digest)