"""One Hermes process per sample, via `--query-file`: no diff text is
shell-interpreted. A non-zero exit is OSError, so the sample retries."""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from .sample import Runner

DEFAULT_BINARY = "hermes"
DEFAULT_TIMEOUT = 900


def hermes_runner(profile: str, *, timeout: int = DEFAULT_TIMEOUT,
                  binary: str = DEFAULT_BINARY,
                  reasoning: str | None = None) -> Runner:
    """Build a runner that asks one Hermes profile one question.

    `reasoning` overrides the profile's `reasoning_effort` for this call. It
    matters: a profile set to `ultra` can spend minutes thinking on a review
    prompt, while the same prompt at `none` answers in seconds.
    """

    def run(prompt: str) -> str:
        with tempfile.TemporaryDirectory(prefix="council-prompt-") as raw:
            path = Path(raw) / "prompt.md"
            path.write_text(prompt, encoding="utf-8", newline="\n")
            argv = [binary, "-p", profile, "chat", "--query-file", str(path),
                    "--oneshot", "-Q"]
            if reasoning is not None:
                argv.extend(["--reasoning", reasoning])
            try:
                proc = subprocess.run(argv, capture_output=True, text=True,
                                      timeout=timeout, check=False)
            except FileNotFoundError as exc:
                raise OSError(f"{binary!r} is not installed or not on PATH") from exc
            except subprocess.TimeoutExpired as exc:
                raise OSError(f"{binary} did not answer within {timeout}s") from exc
        if proc.returncode != 0:
            tail = (proc.stderr or proc.stdout).strip().splitlines()
            raise OSError(f"{binary} exited {proc.returncode}: {tail[-1] if tail else ''}".rstrip())
        return proc.stdout

    return run
