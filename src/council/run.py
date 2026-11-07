"""One review: request in, written run out. The runner is a parameter."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .adjudicate import adjudicate, verdict
from .base import resolve_base
from .config import CONFIG_NAME, load as load_config
from .findings import Finding
from .merge import merge
from .paths import run_dir as run_path
from .prompt import instrument_digest, render
from .proofs import ProofContext
from .sample import Runner, SampleResult, run_sample, write_sample
from .verdict import Result, Verdict

DEFAULT_SAMPLES = 1
DEFAULT_PROFILE = "council-generalist"
MAX_UNTRACKED_BYTES = 200_000


def default_prompt() -> Path:
    """The instrument ships with the tool.

    It is deliberately not read from the repository under review: a prompt
    supplied by the code being judged could ask the reviewer to report nothing,
    and the verdict would look exactly like a clean change.
    """
    return Path(__file__).parent / "prompts" / "reviewer.md"


class ReviewError(RuntimeError):
    """The review cannot start: wrong directory, no prompt, no base."""


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

    @property
    def verdict(self) -> Verdict:
        return self.result.verdict

    @property
    def findings(self) -> tuple[Finding, ...]:
        return self.result.findings

    @property
    def exit_code(self) -> int:
        return self.result.exit_code


def _git(repo: Path, *args: str) -> str:
    proc = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, timeout=60)
    if proc.returncode != 0:
        raise ReviewError(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc.stdout


def _untracked_diff(root: Path) -> str:
    """New files are part of the change; `git diff` does not show them."""
    proc = subprocess.run(["git", "ls-files", "--others", "--exclude-standard", "-z"],
                          cwd=root, capture_output=True, timeout=60)
    if proc.returncode != 0:
        raise ReviewError(f"git ls-files failed: {proc.stderr.decode(errors='replace').strip()}")
    patches: list[str] = []
    for raw in proc.stdout.split(b"\0"):
        if not raw:
            continue
        rel = raw.decode("utf-8", "surrogateescape")
        if rel.startswith(".council/"):
            continue
        try:
            data = (root / rel).read_bytes()
        except OSError:
            continue
        if len(data) > MAX_UNTRACKED_BYTES or b"\0" in data[:8000]:
            continue
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            continue
        body = "".join(f"+{line}\n" for line in text.splitlines())
        patches.append(f"diff --git a/{rel} b/{rel}\nnew file mode 100644\n--- /dev/null\n"
                       f"+++ b/{rel}\n@@ -0,0 +1,{len(text.splitlines())} @@\n{body}")
    return "".join(patches)


def _diff(root: Path, base: str) -> str:
    """The change as a patch: tracked edits, plus new files git leaves out."""
    tracked = _git(root, "-c", "color.ui=false", "diff", "--no-color", "--no-ext-diff", base)
    return tracked + _untracked_diff(root)


def repo_root(path: Path) -> Path:
    """The top of the worktree; a review is about a repository, not a subdirectory."""
    try:
        return Path(_git(path, "rev-parse", "--show-toplevel").strip())
    except (OSError, ReviewError) as exc:
        raise ReviewError(f"{path} is not inside a git repository: {exc}") from exc


def state_dir_ignored(root: Path) -> bool:
    """Whether `.council/` is ignored here, so a review does not dirty `git status`."""
    proc = subprocess.run(["git", "check-ignore", "-q", ".council"], cwd=root,
                          capture_output=True, text=True, timeout=30)
    return proc.returncode == 0


IGNORE_LINE = ".council/"


def init(repo: Path) -> bool:
    """Add `.council/` to the repository's `.gitignore`. True if it was added."""
    root = repo_root(repo)
    path = root / ".gitignore"
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    if any(line.strip().rstrip("/") == ".council" for line in existing.splitlines()):
        return False
    prefix = "" if not existing or existing.endswith("\n") else "\n"
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(f"{prefix}{IGNORE_LINE}\n")
    return True


def _write_verdict(run_dir: Path, request: ReviewRequest, base: str, head: str,
                   digest: str, prompt: Path, ignored: bool,
                   samples: tuple[SampleResult, ...], result: Result) -> None:
    payload = {
        "run": run_dir.name,
        "base": base,
        "head": head,
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
    head = _git(root, "rev-parse", "HEAD").strip()
    diff = _diff(root, base)

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
    if directory.exists():
        raise ReviewError(f"run {run_id!r} already exists at {directory}")

    prompt = render(template, base=base, diff=diff)
    samples = tuple(run_sample(prompt, runner, index=index)
                    for index in range(1, request.samples + 1))
    for sample in samples:
        write_sample(directory, sample)

    config = load_config(root / CONFIG_NAME)
    merged = merge(samples)
    adjudication = adjudicate(
        merged,
        ProofContext(repo=root, allow=config.allow, diff=diff, timeout=config.timeout),
        failed_samples=[sample.index for sample in samples if not sample.ok],
    )
    result = verdict(adjudication)
    ignored = state_dir_ignored(root)
    _write_verdict(directory, request, base, head, digest, prompt_file, ignored,
                   samples, result)
    return Report(directory, base, head, digest, result, samples, prompt_file, ignored)