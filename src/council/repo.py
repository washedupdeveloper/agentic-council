"""Every git call, in one place.

`git()` returns the completed process, for a probe where a missing ref is a
question rather than a failure. `output()` returns stdout and refuses to go on
when git itself failed. One argument list, one timeout, one place to fix quoting.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

GIT_TIMEOUT = 60
IGNORE_LINE = ".council/"
MAX_UNTRACKED_BYTES = 200_000


class ReviewError(RuntimeError):
    """The review cannot start: wrong directory, no prompt, no base."""


def git(repo: Path, *args: str, timeout: int = GIT_TIMEOUT) -> subprocess.CompletedProcess[str]:
    """Run git and hand back the result, whatever it is.

    `surrogateescape` keeps a path that is not valid UTF-8 readable instead of
    raising while a diff is being built.
    """
    return subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True,
        errors="surrogateescape", timeout=timeout,
    )


def output(repo: Path, *args: str, timeout: int = GIT_TIMEOUT) -> str:
    proc = git(repo, *args, timeout=timeout)
    if proc.returncode != 0:
        raise ReviewError(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc.stdout


def untracked_diff(root: Path) -> str:
    """New files are part of the change; `git diff` does not show them."""
    proc = git(root, "ls-files", "--others", "--exclude-standard", "-z")
    if proc.returncode != 0:
        raise ReviewError(f"git ls-files failed: {proc.stderr.strip()}")
    patches: list[str] = []
    for rel in proc.stdout.split("\0"):
        if not rel or rel.startswith(".council/"):
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


def diff(root: Path, base: str) -> str:
    """The change as a patch: tracked edits, plus new files git leaves out."""
    tracked = output(root, "-c", "color.ui=false", "-c", "diff.srcPrefix=a/",
                     "-c", "diff.dstPrefix=b/", "diff", "--no-color", "--no-ext-diff", base)
    return tracked + untracked_diff(root)


def root(path: Path) -> Path:
    """The top of the worktree; a review is about a repository, not a subdirectory."""
    try:
        return Path(output(path, "rev-parse", "--show-toplevel").strip())
    except (OSError, ReviewError) as exc:
        raise ReviewError(f"{path} is not inside a git repository: {exc}") from exc


def state_dir_ignored(root: Path) -> bool:
    """Whether `.council/` is ignored here, so a review does not dirty `git status`."""
    return git(root, "check-ignore", "-q", ".council", timeout=30).returncode == 0


def init(repo: Path) -> bool:
    """Add `.council/` to the repository's `.gitignore`. True if it was added."""
    top = root(repo)
    path = top / ".gitignore"
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    if any(line.strip().rstrip("/") == ".council" for line in existing.splitlines()):
        return False
    prefix = "" if not existing or existing.endswith("\n") else "\n"
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(f"{prefix}{IGNORE_LINE}\n")
    return True