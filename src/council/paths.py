"""Artefacts live at `<repo>/.council/runs/<id>/`: inside the checkout,
gitignored, one path segment per id."""

from __future__ import annotations

from pathlib import Path

#: The directory name inside the repository. Gitignored by `council init`; a
#: review never writes outside the checkout it was asked about.
STATE_DIR = ".council"
RUNS = "runs"


def runs_root(repo: Path) -> Path:
    """The directory holding every run for one repository."""
    return repo / STATE_DIR / RUNS


def run_dir(repo: Path, run_id: str) -> Path:
    """The directory for one run.

    `run_id` is a single path segment. Rejecting separators here is what keeps
    `--run ../../etc` from writing outside the checkout.
    """
    if not run_id or run_id in {".", ".."} or "/" in run_id or "\\" in run_id:
        raise ValueError(f"invalid run id {run_id!r}: expected one path segment")
    return runs_root(repo) / run_id