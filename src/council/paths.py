"""Where a run's artefacts live.

Inside the repository, in a gitignored directory, so a run is inspectable beside
the code it is about — `.council/runs/<id>/`. The shape is the one a cache would
have (`runs/<id>`), but the location is local: a review is evidence about this
checkout, and moving it to a global cache separates it from the thing it
describes.
"""

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