"""Artefacts live at `<repo>/.council/runs/<id>/`: inside the checkout,
gitignored, one path segment per id.

The run-id *name* is validated by the pure `council.domain.run_id`; this
module adds the file-system guard that refuses a symlinked state directory.
"""

from __future__ import annotations

import os
from pathlib import Path

from .domain.run_id import MAX_RUN_ID, validate_run_id

#: The directory name inside the repository. Gitignored by `council init`; a
#: review never writes outside the checkout it was asked about.
STATE_DIR = ".council"
RUNS = "runs"

__all__ = ["MAX_RUN_ID", "RUNS", "STATE_DIR", "cache_runs_root", "run_dir", "runs_root",
           "state_root", "validate_run_id"]


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


def cache_runs_root() -> Path:
    """The per-user state root used by the protocol servers.

    It is deliberately outside the reviewed checkout: a server can retain
    evidence for many repositories without writing into any of them.
    """
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA",
                                   str(Path.home() / "AppData" / "Local")))
    else:
        configured = os.environ.get("XDG_CACHE_HOME")
        base = Path(configured) if configured else Path.home() / ".cache"
    return base / "council" / "runs"
