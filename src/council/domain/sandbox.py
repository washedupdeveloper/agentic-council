"""Pure sandbox argv construction.

The caller resolves `bwrap`, the repository and the inherited `PATH`; this
module decides the argument list. No lookup, no environment read, no process.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

BWRAP = "bwrap"


def reviewer(argv: Sequence[str], prompt_dir: Path, *, bwrap: str,
             binary: str, home: str) -> list[str]:
    """The reviewer's sandbox: read-only host, private /tmp, overlay HOME.

    The reviewer may read the host and reach the network by design; its writes
    are discarded. The prompt directory and binary are bound back because the
    private `/tmp` and overlay would otherwise hide them.
    """
    return [
        bwrap, "--die-with-parent", "--unshare-pid",
        "--ro-bind", "/", "/",
        "--dev", "/dev", "--proc", "/proc", "--tmpfs", "/tmp",
        "--ro-bind", str(prompt_dir), str(prompt_dir),
        "--ro-bind", binary, binary,
        "--overlay-src", home, "--tmp-overlay", home,
        "--chdir", "/", "--", *argv,
    ]


def command(argv: Sequence[str], repo: Path, *, bwrap: str,
            path: str = "/usr/bin:/bin",
            masked: Sequence[str] = ("/home", "/root")) -> list[str]:
    """The bubblewrap invocation for one command, given already-resolved inputs.

    `masked` is checked by the caller for existence: a build sandbox may have no
    `/home` at all, and `--tmpfs` on a missing path is a failure rather than a
    mask. The pure module cannot stat, so the decision stays with the effect.
    """
    target = Path(repo)
    # A repo under /tmp lives under the tmpfs; create its mountpoint first.
    mountpoint = ["--dir", str(target.parent)] if target.is_relative_to("/tmp") else []
    # The masked directories are masked after the host root bind. A repo living
    # under one of them is bound back read-only before the overlay, so masking
    # does not hide the work the command was asked to do.
    home_mounts: list[str] = []
    for name in masked:
        if target.is_relative_to(name):
            home_mounts = ["--dir", str(target.parent), "--ro-bind", str(target), str(target)]
            break
    return [
        bwrap,
        "--unshare-all",        # net, pid, ipc, uts, cgroup, user
        "--die-with-parent",
        "--clearenv",
        "--ro-bind", "/", "/",
        "--dev", "/dev",
        "--proc", "/proc",
        "--tmpfs", "/tmp",
        *(pair for name in masked for pair in ("--tmpfs", name)),
        *mountpoint,
        *home_mounts,
        "--overlay-src", str(target), "--tmp-overlay", str(target),
        "--chdir", str(target),
        "--setenv", "PATH", path,
        "--setenv", "HOME", "/tmp",
        "--setenv", "TMPDIR", "/tmp",
        "--setenv", "LANG", "C.UTF-8",
        "--setenv", "PYTHONDONTWRITEBYTECODE", "1",
        "--setenv", "PYTEST_ADDOPTS", "-p no:cacheprovider",
        "--",
        *argv,
    ]
