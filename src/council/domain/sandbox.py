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
            path: str = "/usr/bin:/bin") -> list[str]:
    """The bubblewrap invocation for one command, given already-resolved inputs."""
    target = Path(repo)
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
        "--setenv", "PATH", path,
        "--setenv", "HOME", "/tmp",
        "--setenv", "TMPDIR", "/tmp",
        "--setenv", "LANG", "C.UTF-8",
        "--setenv", "PYTHONDONTWRITEBYTECODE", "1",
        "--setenv", "PYTEST_ADDOPTS", "-p no:cacheprovider",
        "--",
        *argv,
    ]
