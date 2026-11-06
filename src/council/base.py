"""The revision a review is taken against.

A diff needs a left-hand side, and guessing one silently is how a review of the
wrong change looks exactly like a review of the right one. The order is fixed
and each step is checked against the repository:

1. `--base <rev>`, if given — and a ref that does not resolve is an error, not
   a fallback, because the caller asked for something specific;
2. the merge-base with `origin/HEAD`, which is what a pull request means;
3. `HEAD~1`;
4. otherwise refuse, naming all three.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

GIT_TIMEOUT = 30


class BaseError(ValueError):
    """No usable base revision, or the one asked for does not exist."""


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True, timeout=GIT_TIMEOUT
    )


def _commit(repo: Path, rev: str) -> str | None:
    """The commit id `rev` names, or None when it does not name one here."""
    proc = _git(repo, "rev-parse", "--verify", "--quiet", f"{rev}^{{commit}}")
    if proc.returncode != 0:
        return None
    sha = proc.stdout.strip()
    return sha or None


def resolve_base(repo: Path, explicit: str | None = None) -> str:
    """Resolve the base revision to a commit id, or raise `BaseError`."""
    if explicit is not None:
        sha = _commit(repo, explicit)
        if sha is None:
            raise BaseError(f"--base {explicit!r} is not a revision in this repository")
        return sha

    if _commit(repo, "origin/HEAD") is not None:
        merge_base = _git(repo, "merge-base", "origin/HEAD", "HEAD")
        if merge_base.returncode == 0:
            sha = merge_base.stdout.strip()
            if sha:
                return sha

    previous = _commit(repo, "HEAD~1")
    if previous is not None:
        return previous

    raise BaseError(
        "no base revision: this repository has no origin/HEAD and no HEAD~1, "
        "and no --base was given"
    )