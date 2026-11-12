"""Every git call, in one place.

`git()` returns the completed process, for a probe where a missing ref is a
question rather than a failure. `output()` returns stdout and refuses to go on
when git itself failed. One argument list, one timeout, one place to fix quoting.
"""

from __future__ import annotations

import stat
import subprocess
from dataclasses import dataclass
from pathlib import Path

GIT_TIMEOUT = 60
IGNORE_LINE = ".council/"
MAX_UNTRACKED_BYTES = 200_000


class ReviewError(RuntimeError):
    """The review cannot start: wrong directory, no prompt, no base."""


@dataclass(frozen=True, slots=True)
class Skipped:
    """A file in the change that the diff could not carry, and why."""

    path: str
    reason: str


@dataclass(frozen=True, slots=True)
class Change:
    """The patch under review, and what it could not include."""

    patch: str
    skipped: tuple[Skipped, ...] = ()


def git(repo: Path, *args: str, timeout: int = GIT_TIMEOUT) -> subprocess.CompletedProcess[str]:
    """Run git and hand back the result, whatever it is.

    `surrogateescape` keeps a path that is not valid UTF-8 readable instead of
    raising while a diff is being built.
    """
    try:
        return subprocess.run(
            ["git", *args], cwd=repo, capture_output=True, text=True,
            errors="surrogateescape", timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        raise ReviewError(f"git {' '.join(args)} could not run: {exc}") from exc


def output(repo: Path, *args: str, timeout: int = GIT_TIMEOUT) -> str:
    proc = git(repo, *args, timeout=timeout)
    if proc.returncode != 0:
        raise ReviewError(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc.stdout


def untracked_diff(root: Path) -> tuple[str, tuple[Skipped, ...]]:
    """New files are part of the change; `git diff` does not show them.

    A file too large, binary, unreadable or not UTF-8 cannot be carried by a
    text diff. It is named in `skipped` rather than dropped, so a run says what
    it did not look at.
    """
    proc = git(root, "ls-files", "--others", "--exclude-standard", "-z")
    if proc.returncode != 0:
        raise ReviewError(f"git ls-files failed: {proc.stderr.strip()}")
    patches: list[str] = []
    skipped: list[Skipped] = []
    for rel in proc.stdout.split("\0"):
        if not rel or rel.startswith(".council/"):
            continue
        try:
            info = (root / rel).lstat()
        except OSError:
            skipped.append(Skipped(rel, "unreadable"))
            continue
        if stat.S_ISLNK(info.st_mode):
            skipped.append(Skipped(rel, "symlink"))
            continue
        if not stat.S_ISREG(info.st_mode):
            skipped.append(Skipped(rel, "not a regular file"))
            continue
        try:
            data = (root / rel).read_bytes()
        except OSError:
            skipped.append(Skipped(rel, "unreadable"))
            continue
        if len(data) > MAX_UNTRACKED_BYTES:
            skipped.append(Skipped(rel, "too large"))
            continue
        if b"\0" in data[:8000]:
            skipped.append(Skipped(rel, "binary"))
            continue
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            skipped.append(Skipped(rel, "not utf-8"))
            continue
        body = "".join(f"+{line}\n" for line in text.splitlines())
        patches.append(f"diff --git a/{rel} b/{rel}\nnew file mode 100644\n--- /dev/null\n"
                       f"+++ b/{rel}\n@@ -0,0 +1,{len(text.splitlines())} @@\n{body}")
    return "".join(patches), tuple(skipped)


def diff(root: Path, base: str, *, staged: bool = False) -> Change:
    """The change as a patch: tracked edits, plus new files git leaves out.

    `staged` reads the index against the base, not the working tree. It is the
    exact question "what would this commit contain?"; unstaged edits and
    untracked files are deliberately absent.
    """
    options = ["-c", "color.ui=false", "-c", "diff.srcPrefix=a/",
               "-c", "diff.dstPrefix=b/", "diff", "--no-color", "--no-ext-diff"]
    if staged:
        options.append("--cached")
    tracked = output(root, *options, base)
    if staged:
        return Change(tracked)
    untracked, skipped = untracked_diff(root)
    return Change(tracked + untracked, skipped)


def root(path: Path) -> Path:
    """The top of the worktree; a review is about a repository, not a subdirectory."""
    try:
        return Path(output(path, "rev-parse", "--show-toplevel").strip())
    except (OSError, ReviewError) as exc:
        raise ReviewError(f"{path} is not inside a git repository: {exc}") from exc


def state_dir_ignored(root: Path) -> bool:
    """Whether `.council/` is ignored here, so a review does not dirty `git status`."""
    return git(root, "check-ignore", "-q", ".council", timeout=30).returncode == 0


def python_files(root: Path) -> tuple[str, ...]:
    """Every Python file the checkout has, tracked or new — the context's search space."""
    proc = git(root, "ls-files", "-z", "--cached", "--others", "--exclude-standard", "--", "*.py")
    if proc.returncode != 0:
        raise ReviewError(f"git ls-files failed: {proc.stderr.strip()}")
    return tuple(rel for rel in proc.stdout.split("\0") if rel)


def init(repo: Path) -> bool:
    """Add `.council/` to the repository's `.gitignore`. True if it was added."""
    top = root(repo)
    path = top / ".gitignore"
    try:
        if path.is_symlink():
            raise ReviewError(f"{path} is a symlink: refusing to write outside the checkout")
        if path.exists() and not path.is_file():
            raise ReviewError(f"{path} is not a regular file")
        existing = path.read_text(encoding="utf-8") if path.exists() else ""
        if any(line.strip().lstrip("/").rstrip("/") == ".council"
               for line in existing.splitlines()):
            return False
        prefix = "" if not existing or existing.endswith("\n") else "\n"
        with path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(f"{prefix}{IGNORE_LINE}\n")
    except ReviewError:
        raise
    except (OSError, UnicodeDecodeError) as exc:
        raise ReviewError(f"cannot update {path}: {exc}") from exc
    return True
