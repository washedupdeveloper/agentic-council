"""The boundary a `command` proof runs in.

bubblewrap, one process: no network, a read-only root, a private `/tmp` and
`$HOME`, and a cleared environment. The repository is an overlay with a tmpfs
upper — a proof may write, and the writes vanish when it exits.

A write outside the repository (and outside `/tmp`) is EROFS, reported as
`UNRUNNABLE` (the check could not be made), never as a refutation.
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
        "--overlay-src", str(target), "--tmp-overlay", str(target),
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
