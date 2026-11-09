"""The base: `--base`, else merge-base with `origin/HEAD`, else `HEAD~1`, else
refuse. A wrong base looks like a healthy review, so each step is checked."""

from __future__ import annotations

from pathlib import Path

from .repo import git


class BaseError(ValueError):
    """No usable base revision, or the one asked for does not exist."""


def _commit(repo: Path, rev: str) -> str | None:
    """The commit id `rev` names, or None when it does not name one here."""
    proc = git(repo, "rev-parse", "--verify", "--quiet", f"{rev}^{{commit}}")
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
        merge_base = git(repo, "merge-base", "origin/HEAD", "HEAD")
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
