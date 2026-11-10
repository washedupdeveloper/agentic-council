"""A GitHub pull request: resolve it with `gh`, then verify the checkout is it.

The tool does not check anything out. A review of a PR is a review of a commit;
silently switching branches or reviewing a dirty worktree would make the verdict
describe something other than the pull request.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .repo import ReviewError, output

FIELDS = "number,url,title,baseRefOid,headRefOid,baseRefName,headRefName"


@dataclass(frozen=True, slots=True)
class PullRequest:
    number: int
    url: str
    title: str
    base: str
    head: str
    base_ref: str
    head_ref: str


def resolve(number: int, repo: Path, *, gh: str = "gh") -> PullRequest:
    """Ask `gh` for the PR's base and head SHAs."""
    if number < 1:
        raise ReviewError("a pull request number is a positive integer")
    binary = shutil.which(gh)
    if binary is None:
        raise ReviewError("`gh` is not installed or not on PATH: `council pr` needs the GitHub CLI")
    proc = subprocess.run([binary, "pr", "view", str(number), "--json", FIELDS],
                          cwd=repo, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        detail = proc.stderr.strip() or proc.stdout.strip() or f"exit {proc.returncode}"
        raise ReviewError(f"gh pr view {number} failed: {detail}")
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise ReviewError(f"gh pr view {number} returned no JSON") from exc
    try:
        return PullRequest(int(data["number"]), str(data["url"]), str(data["title"]),
                           str(data["baseRefOid"]), str(data["headRefOid"]),
                           str(data["baseRefName"]), str(data["headRefName"]))
    except (KeyError, TypeError, ValueError) as exc:
        raise ReviewError(f"gh pr view {number} returned an incomplete pull request") from exc


def verify_checkout(pr: PullRequest, repo: Path) -> None:
    """The reviewed tree must be exactly the PR's head commit, with no local edits."""
    head = output(repo, "rev-parse", "HEAD").strip()
    if head != pr.head:
        raise ReviewError(
            f"the checkout is {head[:12]}, but PR #{pr.number} is {pr.head[:12]}: "
            f"run `gh pr checkout {pr.number}` first")
    dirty = output(repo, "status", "--porcelain")
    if dirty.strip():
        raise ReviewError(
            "the worktree has local changes; a PR review is the commit, not the worktree")
