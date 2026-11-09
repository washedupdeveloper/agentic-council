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
from .findings import Finding, blocks
from .merge import merge
from .paths import run_dir as run_path
from .prompt import instrument_digest, render
from .proofs import ProofContext
from .reference import FetchError, Reference, fetch
from .repo import (ReviewError, Skipped, diff, output, python_files,
                   root as repo_root, state_dir_ignored)
from .sample import Runner, SampleResult, run_sample, write_sample
from .verdict import Result, Verdict

DEFAULT_PROFILE = "council-generalist"
AUTO_MAX = 3
# A prompt past this size is not sent to the reviewer without a person's word.
# The failure is silent and expensive otherwise: the model can sit for its whole
# timeout and the sample is retried once.
PROMPT_LIMIT = 32 * 1024


class PromptTooLarge(ReviewError):
    """The prompt is over the limit and nobody has allowed it."""

    def __init__(self, size: int, limit: int, *, declined: bool = False) -> None:
        self.size = size
        self.limit = limit
        if declined:
            tail = "Nothing was asked: proceeding was declined."
        else:
            tail = ("Nothing was asked. Narrow the change with --base, raise the "
                    "budget with --max-prompt-bytes, or allow it with "
                    "--allow-large-prompt.")
        super().__init__(
            f"the prompt is {size:,} bytes; the limit is {limit:,}. {tail}")


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
                   prompt_acknowledged: bool) -> None:
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
        "state_dir_ignored": ignored,
        "profile": request.profile,
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
    context = build_context(patch, _reader(root), python_files(root),
                           max_depth=request.context_depth - 1)
    try:
        references = tuple(fetch(url) for url in request.context_urls)
    except FetchError as exc:
        raise ReviewError(str(exc)) from exc
    prompt_context = context.text
    if references:
        prompt_context = f"{prompt_context}\n\n{_reference_text(references)}"

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

    prompt = render(template, base=base, diff=patch, context=prompt_context)
    prompt_bytes = len(prompt.encode("utf-8"))
    limit = request.max_prompt_bytes
    acknowledged = request.allow_large_prompt
    if prompt_bytes > limit and not acknowledged:
        raise PromptTooLarge(prompt_bytes, limit)
    samples, samples_run, agreement = _samples(prompt, runner, request.samples)
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
                   skipped=change.skipped, context=context, references=references,
                   samples_run=samples_run, agreement=agreement,
                   prompt_bytes=prompt_bytes, prompt_limit=limit,
                   prompt_acknowledged=acknowledged)
    return Report(directory, base, head, digest, result, samples, prompt_file, ignored,
                  change.skipped, diff_sha256, context.digest)