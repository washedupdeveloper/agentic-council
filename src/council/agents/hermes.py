"""Hermes Agent CLI: one profile answered through ``--query-file``."""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from ..runner import DEFAULT_IDLE_TIMEOUT, DEFAULT_TIMEOUT, _read_stream, _sandbox_argv
from ..sample import ReviewerMissing, Runner
from .base import AgentIdentity, AgentOptions

DEFAULT_BINARY = "hermes"
#: A profile's own configuration, in the order Hermes writes it. Both are read
#: when present: `config.yaml` carries the model, `profile.yaml` the persona.
PROFILE_CONFIG_FILES = ("config.yaml", "profile.yaml")


def hermes_runner(profile: str, *, timeout: int = DEFAULT_TIMEOUT,
                  binary: str = DEFAULT_BINARY,
                  reasoning: str | None = None,
                  stream: bool = False,
                  idle_timeout: int = DEFAULT_IDLE_TIMEOUT,
                  sandbox: bool = False) -> Runner:
    """Build a runner that asks one Hermes profile one question.

    `reasoning` overrides the profile's `reasoning_effort` for this call.
    `stream` reads the answer as JSON events and kills a silent request after
    `idle_timeout` seconds, so a stalled provider fails fast.
    """
    binary = binary or DEFAULT_BINARY

    def run(prompt: str) -> str:
        with tempfile.TemporaryDirectory(prefix="council-prompt-") as raw:
            path = Path(raw) / "prompt.md"
            path.write_text(prompt, encoding="utf-8", newline="\n")
            argv = [binary, "-p", profile, "chat", "--query-file", str(path),
                    "--oneshot", "-Q"]
            if reasoning is not None:
                argv.extend(["--reasoning", reasoning])
            if sandbox:
                argv = _sandbox_argv(argv, path.parent)
            if stream:
                argv.extend(["--format", "stream-json"])
                return _read_stream(argv, timeout, idle_timeout)
            try:
                proc = subprocess.run(argv, capture_output=True, text=True,
                                      errors="replace", timeout=timeout, check=False)
            except (FileNotFoundError, PermissionError, NotADirectoryError, ValueError) as exc:
                raise ReviewerMissing(f"{binary!r} is not installed or not executable") from exc
            except subprocess.TimeoutExpired as exc:
                raise OSError(f"{binary} did not answer within {timeout}s") from exc
        if proc.returncode != 0:
            tail = (proc.stderr or proc.stdout).strip().splitlines()
            raise OSError(f"{binary} exited {proc.returncode}: {tail[-1] if tail else ''}".rstrip())
        return proc.stdout

    return run


@dataclass(frozen=True, slots=True)
class ProfileFingerprint:
    """A reviewer's configuration, identified without parsing it.

    The model, provider, reasoning default and every prompt-affecting setting
    live in the profile's own configuration, which this tool deliberately does
    not parse: it is another program's format, and a parser that guessed would be
    wrong silently. Hashing the bytes is the conservative direction. A profile
    edited for an unrelated setting breaks the digest, so two runs are reported
    as different instruments — that costs a comparison, never a verdict. A missed
    model swap would let two instruments be compared as one, which is the failure
    this exists to prevent.
    """

    path: str = ""
    sha256: str = ""


def hermes_home() -> Path:
    """Where Hermes keeps its profiles: `$HERMES_HOME`, else `~/.hermes`."""
    configured = os.environ.get("HERMES_HOME")
    return Path(configured) if configured else Path.home() / ".hermes"


def profile_fingerprint(profile: str) -> ProfileFingerprint:
    """Digest the configuration a review's samples are asked under.

    A profile names one directory under the Hermes home; it is not a path, and a
    value that tries to be one is not read. A missing profile is reported as
    missing, never as an empty match.
    """
    if not profile or profile in {".", ".."} or "/" in profile or "\\" in profile:
        return ProfileFingerprint()
    try:
        home = hermes_home()
    except RuntimeError:
        # No HOME to resolve a default from. An unknown instrument is the honest
        # answer; a traceback on every review is not.
        return ProfileFingerprint()
    directory = home / "profiles" / profile
    digest = hashlib.sha256()
    found = ""
    for name in PROFILE_CONFIG_FILES:
        try:
            data = (directory / name).read_bytes()
        except (OSError, ValueError):
            continue
        digest.update(name.encode("utf-8"))
        digest.update(b"\x00")
        digest.update(data)
        digest.update(b"\x00")
        if not found:
            found = f"profiles/{profile}/{name}"
    if not found:
        return ProfileFingerprint()
    return ProfileFingerprint(found, digest.hexdigest()[:16])


class HermesAdapter:
    """The only shipped reviewer adapter."""

    name = "hermes"
    description = "Hermes Agent CLI, one profile per sample"
    profile_required = True
    default_binary = DEFAULT_BINARY

    def runner(self, options: AgentOptions) -> Runner:
        return hermes_runner(options.profile, binary=options.binary,
                             timeout=options.timeout, reasoning=options.reasoning,
                             stream=options.stream, idle_timeout=options.idle_timeout,
                             sandbox=options.sandbox)

    def identity(self, options: AgentOptions) -> AgentIdentity:
        fingerprint = profile_fingerprint(options.profile)
        return AgentIdentity("hermes", profile=options.profile,
                             source=fingerprint.path, sha256=fingerprint.sha256)

    def available(self, options: AgentOptions) -> tuple[bool, str]:
        try:
            binary = options.binary or DEFAULT_BINARY
            located = shutil.which(binary)
            if located is not None:
                return True, str(Path(located).resolve())
            candidate = Path(binary)
            if candidate.is_file() and os.access(candidate, os.X_OK):
                return True, str(candidate.resolve())
        except (OSError, ValueError) as exc:
            return False, f"{options.binary or DEFAULT_BINARY}: {exc}"
        return False, f"{options.binary or DEFAULT_BINARY} is not installed or not on PATH"
