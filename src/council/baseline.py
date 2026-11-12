"""Read, write and snapshot baselines.

The decisions are in `council.domain.baseline`; this module is the file/git
effect shell. A baseline is a regular UTF-8 JSON file, never a symlink or FIFO.
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import date
from pathlib import Path, PurePosixPath

from .domain.baseline import (
    Baseline,
    BaselineError as DomainBaselineError,
    from_findings,
    parse as parse_baseline,
    render as render_baseline,
)
from .findings import Finding, State, blocks
from .repo import ReviewError, output

MAX_BASELINE_BYTES = 1_000_000


class BaselineError(ReviewError):
    """A baseline cannot be read, written or used."""


def load(path: Path) -> Baseline:
    """Load a baseline from the working tree, refusing non-regular files."""
    try:
        if path.is_symlink():
            raise BaselineError(f"{path} is a symlink: a baseline must be a regular file")
        if not path.exists():
            raise BaselineError(f"no baseline at {path}")
        if not path.is_file():
            raise BaselineError(f"{path} is not a regular file")
        if path.stat().st_size > MAX_BASELINE_BYTES:
            raise BaselineError(f"{path} is larger than {MAX_BASELINE_BYTES:,} bytes")
        text = path.read_text(encoding="utf-8")
    except BaselineError:
        raise
    except (OSError, UnicodeDecodeError) as exc:
        raise BaselineError(f"cannot read baseline {path}: {exc}") from exc
    try:
        return parse_baseline(text)
    except DomainBaselineError as exc:
        raise BaselineError(f"{path}: {exc}") from exc


def load_at(repo: Path, revision: str, relative: str) -> Baseline:
    """Load a baseline from a committed revision, not the working tree.

    This is the CI trust boundary: a pull request cannot edit its own baseline
    to hide a new finding. The path must stay below the repository root.
    """
    rel = _relative(relative)
    try:
        text = output(repo, "show", f"{revision}:{rel}")
    except ReviewError as exc:
        raise BaselineError(
            f"cannot read baseline {rel} at {revision}: {exc}") from exc
    try:
        size = len(text.encode("utf-8"))
    except UnicodeEncodeError as exc:
        raise BaselineError(f"{rel} at {revision} is not UTF-8") from exc
    if size > MAX_BASELINE_BYTES:
        raise BaselineError(f"{rel} at {revision} is larger than {MAX_BASELINE_BYTES:,} bytes")
    try:
        return parse_baseline(text)
    except DomainBaselineError as exc:
        raise BaselineError(f"{rel} at {revision}: {exc}") from exc


def write(path: Path, baseline: Baseline) -> None:
    """Atomically replace a baseline with its canonical form."""
    try:
        if path.is_symlink():
            raise BaselineError(f"{path} is a symlink: refusing to write through it")
        if not path.parent.exists():
            raise BaselineError(f"baseline parent {path.parent} does not exist")
        if not path.parent.is_dir():
            raise BaselineError(f"baseline parent {path.parent} is not a directory")
        fd, raw = tempfile.mkstemp(prefix=".council-baseline-", dir=path.parent)
        temp = Path(raw)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(render_baseline(baseline))
            os.replace(temp, path)
        finally:
            try:
                temp.unlink(missing_ok=True)
            except OSError:
                pass
    except BaselineError:
        raise
    except (OSError, ValueError) as exc:
        raise BaselineError(f"cannot write baseline {path}: {exc}") from exc


def from_run(run_dir: Path, *, owner: str, reason: str, created: date,
             expires: date) -> Baseline:
    """Snapshot the proven blocking findings in a kept run."""
    findings = run_findings(run_dir)
    try:
        baseline = from_findings(findings, owner=owner, reason=reason,
                                 created=created, expires=expires)
    except DomainBaselineError as exc:
        raise BaselineError(str(exc)) from exc
    if not baseline.entries:
        raise BaselineError(
            f"{run_dir}/verdict.json has no proven blocking findings to baseline")
    return baseline


def run_fingerprints(run_dir: Path) -> set[str]:
    """The fingerprints a current run would match; used by `baseline prune`."""
    from .domain.baseline import fingerprint

    return {fingerprint(finding) for finding in run_findings(run_dir)
            if finding.state is State.PROVEN and finding.blocks}


def run_findings(run_dir: Path) -> tuple[Finding, ...]:
    """Read findings from a run's verdict, without trusting the model again."""
    path = run_dir / "verdict.json"
    try:
        if path.is_symlink():
            raise BaselineError(f"{path} is a symlink")
        if not path.is_file():
            raise BaselineError(f"no verdict at {path}")
        raw = json.loads(path.read_text(encoding="utf-8"))
    except BaselineError:
        raise
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BaselineError(f"cannot read {path}: {exc}") from exc
    if not isinstance(raw, dict) or not isinstance(raw.get("findings"), list):
        raise BaselineError(f"{path} has no findings list")
    if raw.get("verdict") == "incomplete":
        raise BaselineError(f"{path} is an incomplete run; obtain the missing evidence first")
    samples = raw.get("samples", [])
    if isinstance(samples, list) and any(
            isinstance(item, dict) and item.get("ok") is False for item in samples):
        raise BaselineError(f"{path} has a failed sample; it cannot seed or prune a baseline")
    units = raw.get("units", [])
    if isinstance(units, list) and any(
            isinstance(item, dict) and item.get("ok") is False for item in units):
        raise BaselineError(f"{path} has an unreviewed unit; it cannot seed or prune a baseline")
    findings: list[Finding] = []
    for index, item in enumerate(raw["findings"], start=1):
        if not isinstance(item, dict):
            raise BaselineError(f"{path}: finding {index} is not an object")
        try:
            state = State(str(item["state"]))
            dimension = str(item["dimension"])
            severity = str(item["severity"])
            location = str(item["location"])
            claim = str(item["claim"])
            proof = str(item.get("proof", ""))
        except (KeyError, ValueError) as exc:
            raise BaselineError(f"{path}: finding {index} is invalid: {exc}") from exc
        if state is not State.PROVEN or not blocks(dimension, severity):
            continue
        try:
            findings.append(Finding(
                id=str(item.get("id", f"F-{index:02d}")),
                dimension=dimension,
                severity=severity,  # type: ignore[arg-type]
                state=state,
                location=location,
                claim=claim,
                proof=proof,
            ))
        except ValueError as exc:
            raise BaselineError(f"{path}: finding {index} is invalid: {exc}") from exc
    return tuple(findings)


def _relative(raw: str) -> str:
    """A repository-relative POSIX path, or a refusal."""
    if not raw or raw.startswith("/") or raw.startswith("\\"):
        raise BaselineError("--baseline must be a repository-relative path when read from a revision")
    path = PurePosixPath(raw)
    if any(part in {"", ".", ".."} for part in path.parts):
        raise BaselineError(f"invalid baseline path {raw!r}")
    if path.is_absolute():
        raise BaselineError("--baseline must be a repository-relative path")
    return str(path)
