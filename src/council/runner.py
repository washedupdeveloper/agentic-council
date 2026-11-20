"""Process transport shared by reviewer adapters.

An adapter builds its own argv and calls these helpers. A non-zero exit is
``OSError`` so the sample retries; a silent stream is killed at the idle timeout
rather than costing the whole sample timeout.
"""

from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from typing import TextIO

from .domain.sandbox import reviewer as reviewer_argv
from .repo import ReviewError
from .sample import ReviewerMissing

DEFAULT_TIMEOUT = 900
DEFAULT_IDLE_TIMEOUT = 120
SILENCE_POLL = 0.25


def _tail(stream: TextIO) -> str:
    stream.seek(0)
    lines = stream.read().strip().splitlines()
    return f": {lines[-1]}" if lines else ""


def _sandbox_argv(argv: list[str], prompt_dir: Path) -> list[str]:
    """Run the reviewer with a read-only root, a private /tmp and an overlay home.

    The reviewer can read the host and reach the network, but every write lands
    in a tmpfs overlay of `$HOME` or the private `/tmp`; both vanish with the
    process. The prompt directory and the binary are bound back because the
    private `/tmp` would otherwise hide them.
    """
    bwrap = shutil.which("bwrap")
    if bwrap is None:
        raise OSError("bwrap is required for the reviewer sandbox but is not on PATH")
    located = shutil.which(argv[0]) or argv[0]
    # bwrap refuses to mount onto a symlink destination. Resolve the executable
    # first and run that path inside the sandbox, so a Nix profile symlink (or
    # any other shim) does not make an otherwise healthy reviewer unlaunchable.
    binary = str(Path(located).resolve())
    if shutil.which(argv[0]) is None and not Path(argv[0]).is_file():
        raise ReviewerMissing(f"{argv[0]!r} is not installed or not on PATH")
    if not os.access(binary, os.X_OK):
        raise ReviewerMissing(f"{argv[0]!r} is not executable")
    try:
        home = str(Path.home())
    except RuntimeError as exc:
        raise ReviewError("HOME is not set: the reviewer sandbox needs a home to overlay") from exc
    return reviewer_argv([binary, *argv[1:]], prompt_dir, bwrap=bwrap,
                         binary=binary, home=home)


def _terminate(proc: subprocess.Popen[str]) -> None:
    """Kill the reviewer and anything it spawned.

    Killing the direct child is not enough: a wrapper's `sleep` can inherit the
    pipe, and the reader would block forever waiting for an EOF that never
    comes. The process is started in its own session on POSIX so the group can
    be killed as a unit.
    """
    if os.name == "posix":
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            return
        except (ProcessLookupError, PermissionError, OSError):
            pass
    proc.kill()


def _read_stream(argv: list[str], timeout: int, idle_timeout: int) -> str:
    """Read `--format stream-json` events, killing silence at the idle timeout."""
    with tempfile.TemporaryFile(mode="w+", encoding="utf-8") as errors:
        try:
            proc = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=errors,
                                    text=True, errors="replace", bufsize=1,
                                    start_new_session=os.name == "posix")
        except (FileNotFoundError, PermissionError, NotADirectoryError, ValueError) as exc:
            raise ReviewerMissing(f"{argv[0]!r} is not installed or not executable") from exc
        if proc.stdout is None:  # pragma: no cover - PIPE guarantees it
            raise OSError("the reviewer process has no stdout")
        deadline = time.monotonic() + timeout
        last = time.monotonic()
        stopped: list[str] = []

        def watch() -> None:
            while proc.poll() is None:
                now = time.monotonic()
                if now - last >= idle_timeout:
                    stopped.append(f"stream went silent for {idle_timeout}s")
                    _terminate(proc)
                    return
                if now >= deadline:
                    stopped.append(f"did not answer within {timeout}s")
                    _terminate(proc)
                    return
                time.sleep(SILENCE_POLL)

        watcher = threading.Thread(target=watch, daemon=True)
        watcher.start()
        text: list[str] = []
        final: str | None = None
        exit_code: int | None = None
        try:
            for line in proc.stdout:
                last = time.monotonic()
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    event = json.loads(stripped)
                except json.JSONDecodeError:
                    continue
                if not isinstance(event, dict):
                    continue
                kind = event.get("type")
                if kind == "text":
                    text.append(str(event.get("text", "")))
                elif kind == "result":
                    value = event.get("text")
                    final = value if isinstance(value, str) else None
                    code = event.get("exit_code")
                    exit_code = code if isinstance(code, int) else 0
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
                stopped.append("did not exit after its stream ended")
        finally:
            watcher.join(timeout=1)
            if proc.poll() is None:
                _terminate(proc)
                proc.wait()
            if proc.stdout is not None:
                proc.stdout.close()
            errors.seek(0)
            detail = _tail(errors)
        if stopped:
            raise OSError(f"{argv[0]} {stopped[0]}{detail}")
        if exit_code not in (0, None):
            raise OSError(f"{argv[0]} exited {exit_code}{detail}")
        if proc.returncode not in (0, None):
            raise OSError(f"{argv[0]} exited {proc.returncode}{detail}")
        answer = final if final is not None and final.strip() else "".join(text)
        if not answer.strip():
            raise OSError(f"{argv[0]} stream ended without an answer{detail}")
        return answer
