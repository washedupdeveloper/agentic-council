"""The boundary a `command` proof runs in.

bubblewrap, one process: no network, a read-only root, a private `/tmp` and
`$HOME`, and a cleared environment. The repository is an overlay with a tmpfs
upper — a proof may write, and the writes vanish when it exits.

A write outside the repository (and outside `/tmp`) is EROFS, reported as
`UNRUNNABLE` (the check could not be made), never as a refutation.

The argument list itself is decided by the pure `council.domain.sandbox`.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Sequence

from .domain.sandbox import BWRAP, command

__all__ = ["BWRAP", "argv", "available"]


def available() -> bool:
    return shutil.which(BWRAP) is not None


def argv(argv: Sequence[str], repo: Path) -> list[str] | None:
    """Wrap a command, or None when there is no bwrap to wrap it with."""
    bwrap = shutil.which(BWRAP)
    if bwrap is None:
        return None
    return command(
        argv,
        repo.resolve(),
        bwrap=bwrap,
        path=os.environ.get("PATH", "/usr/bin:/bin"),
        masked=masked(),
    )


def masked() -> tuple[str, ...]:
    """Every directory that must not be readable: the homes, then `$HOME`.

    The conventional trees cover most hosts. `$HOME` covers a home placed
    elsewhere (a service account under `/srv`, `/var/lib`, an exported mount),
    which the host-root bind would otherwise expose.
    """
    names = ["/home", "/root"]
    home = os.environ.get("HOME", "")
    if home.startswith("/") and not Path(home).is_relative_to("/tmp"):
        names.append(home)
    seen: list[str] = []
    for name in names:
        if name not in seen and os.path.isdir(name):
            seen.append(name)
    return tuple(seen)
