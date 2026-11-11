"""Artefacts live at `<repo>/.council/runs/<id>/`: inside the checkout,
gitignored, one path segment per id."""

from __future__ import annotations

from pathlib import Path

#: The directory name inside the repository. Gitignored by `council init`; a
#: review never writes outside the checkout it was asked about.
STATE_DIR = ".council"
RUNS = "runs"
MAX_RUN_ID = 128
#: Characters a run id may not contain: separators, control characters, and the
#: set Windows refuses in a file name. A run id is a directory name on every host.
_FORBIDDEN = set('/\\<>:"|?*')


def validate_run_id(run_id: str) -> str:
    """One portable path segment, or a ValueError that names the problem."""
    if not run_id or not run_id.strip():
        raise ValueError("run id must not be empty")
    if run_id in {".", ".."}:
        raise ValueError(f"invalid run id {run_id!r}: expected one path segment")
    if any(ch in _FORBIDDEN for ch in run_id):
        raise ValueError(f"invalid run id {run_id!r}: expected one path segment")
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in run_id):
        raise ValueError(f"invalid run id {run_id!r}: control characters are not allowed")
    if any(0xD800 <= ord(ch) <= 0xDFFF for ch in run_id):
        raise ValueError(f"invalid run id {run_id!r}: not valid UTF-8")
    if len(run_id) > MAX_RUN_ID:
        raise ValueError(f"invalid run id: longer than {MAX_RUN_ID} characters")
    return run_id


def runs_root(repo: Path) -> Path:
    """The directory holding every run for one repository."""
    return repo / STATE_DIR / RUNS


def state_root(repo: Path) -> Path:
    """The runs directory, refusing a symlinked path out of the checkout.

    `run_id` is checked for separators, but a pre-existing `.council` symlink
    would still move every write elsewhere; `is_symlink()` is an lstat, so a
    link is seen even when its target is missing.
    """
    base = repo / STATE_DIR
    for part in (base, base / RUNS):
        if part.is_symlink():
            raise ValueError(f"{part} is a symlink: a run must not write outside the checkout")
        if part.exists() and not part.is_dir():
            raise ValueError(f"{part} is not a directory: a run cannot be written there")
    return base / RUNS


def run_dir(repo: Path, run_id: str) -> Path:
    """The directory for one run.

    `run_id` is a single path segment. Rejecting separators here is what keeps
    `--run ../../etc` from writing outside the checkout.
    """
    return state_root(repo) / validate_run_id(run_id)
