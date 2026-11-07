"""The boundary a `command` proof runs in.

bubblewrap, one process: no network, every mount read-only, a private `/tmp` and
`$HOME`, and a cleared environment. The repository the proof judges is therefore
read-only too — a proof cannot edit the thing it is evidence about.

Read-only is not free: a tool that wants to write into the tree fails with
`EROFS`. That is reported as `UNRUNNABLE` (the check could not be made), never
as a refutation.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Sequence

BWRAP = "bwrap"


def available() -> bool:
    return shutil.which(BWRAP) is not None


def argv(argv: Sequence[str], repo: Path) -> list[str] | None:
    """Wrap a command, or None when there is no bwrap to wrap it with."""
    bwrap = shutil.which(BWRAP)
    if bwrap is None:
        return None
    target = repo.resolve()
    # A repo under /tmp lives under the tmpfs; create its mountpoint first.
    mountpoint = ["--dir", str(target.parent)] if target.is_relative_to("/tmp") else []
    return [
        bwrap,
        "--unshare-all",        # net, pid, ipc, uts, cgroup, user
        "--die-with-parent",
        "--clearenv",
        "--ro-bind", "/", "/",
        "--dev", "/dev",
        "--proc", "/proc",
        "--tmpfs", "/tmp",
        *mountpoint,
        "--ro-bind", str(target), str(target),
        "--chdir", str(target),
        "--setenv", "PATH", os.environ.get("PATH", "/usr/bin:/bin"),
        "--setenv", "HOME", "/tmp",
        "--setenv", "TMPDIR", "/tmp",
        "--setenv", "LANG", "C.UTF-8",
        "--setenv", "PYTHONDONTWRITEBYTECODE", "1",
        "--setenv", "PYTEST_ADDOPTS", "-p no:cacheprovider",
        "--",
        *argv,
    ]