"""Shared process boundary for the optional ACP and MCP adapters.

The adapters deliberately do not import the review engine. They run the public
`council` command and consume its existing `--json` output and exit codes. That
keeps the V2 core untouched: a server upgrade cannot change a verdict, and a
server bug cannot reach into the prompt, proof or evidence code.

Nothing here imports an optional protocol package. `council_mcp` and
`council_acp` import their SDKs; this module remains usable without either.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import signal
import sys
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any
from uuid import uuid4

EventHook = Callable[[str], Awaitable[None]]


class CouncilError(RuntimeError):
    """The public council command could not produce a result."""


@dataclass(frozen=True, slots=True)
class ServerConfig:
    """Deployment choices; never supplied by a protocol client."""

    root: Path
    state_root: Path
    agent: str = "hermes"
    reviewer: str | None = None
    profile: str | None = None
    no_sandbox: bool = False
    timeout: float = 3600.0
    command: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ReviewOptions:
    """The small review surface the protocol adapters expose."""

    repo: str = "."
    base: str | None = None
    include: tuple[str, ...] = ()
    exclude: tuple[str, ...] = ()
    samples: int | None = None
    context_depth: int = 3
    time_budget: int = 0


@dataclass(frozen=True, slots=True)
class CommandResult:
    payload: Any
    returncode: int
    stderr: str
    run_dir: Path | None = None


def default_state_root() -> Path:
    """A per-user evidence cache, never the reviewed repository."""
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local")))
    else:
        configured = os.environ.get("XDG_CACHE_HOME")
        base = Path(configured) if configured else Path.home() / ".cache"
    return base / "council" / "runs"


def _base_command(config: ServerConfig) -> list[str]:
    if config.command:
        return list(config.command)
    override = os.environ.get("COUNCIL_BIN")
    if override:
        return [override]
    found = shutil.which("council")
    if found:
        return [found]
    return [sys.executable, "-m", "council"]


def _child_env() -> dict[str, str]:
    """Make `python -m council` work from a source checkout as well as a wheel."""
    env = os.environ.copy()
    try:
        import council  # noqa: PLC0415 - the package root is the source-ish path
    except ImportError:
        return env
    root = str(Path(council.__file__).resolve().parent.parent)
    current = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = root + (os.pathsep + current if current else "")
    return env


def local_path(raw: str | Path) -> Path:
    """Translate a Windows path when this process runs under WSL.

    Zed on Windows may pass `C:\\work\\repo` to an ACP server launched through
    `wsl.exe`. `Path("C:\\...")` is not an absolute POSIX path, so the server
    would otherwise reject a workspace the editor is actually showing.
    """
    text = str(raw)
    if os.name != "nt" and len(text) >= 3 and text[1] == ":" and text[2] in "\\/":
        return Path("/mnt") / text[0].lower() / text[3:].replace("\\", "/")
    return Path(raw)


def _resolve_repo(config: ServerConfig, repo: str | None) -> Path:
    """Resolve a client path beneath the server's configured repository root."""
    candidate = local_path(repo or ".")
    if not candidate.is_absolute():
        candidate = config.root / candidate
    try:
        resolved = candidate.resolve()
        root = config.root.resolve()
    except (OSError, RuntimeError, ValueError) as exc:
        raise CouncilError(f"cannot resolve repository {candidate}: {exc}") from exc
    if not resolved.is_relative_to(root):
        raise CouncilError(f"repository {resolved} is outside the server root {root}")
    if not resolved.is_dir():
        raise CouncilError(f"repository {resolved} is not a directory")
    return resolved


def _append_review_args(config: ServerConfig, options: ReviewOptions,
                        argv: list[str]) -> None:
    if options.base is not None:
        argv.extend(["--base", options.base])
    for pattern in options.include:
        argv.extend(["--include", pattern])
    for pattern in options.exclude:
        argv.extend(["--exclude", pattern])
    if options.samples is not None:
        argv.extend(["--samples", str(options.samples)])
    argv.extend(["--context-depth", str(options.context_depth)])
    if options.time_budget:
        argv.extend(["--time-budget", str(options.time_budget)])
    argv.extend(["--agent", config.agent])
    if config.profile:
        argv.extend(["--profile", config.profile])
    if config.reviewer:
        argv.extend(["--reviewer", config.reviewer])
    if config.no_sandbox:
        argv.append("--no-sandbox")


def _kill(proc: asyncio.subprocess.Process) -> None:
    if os.name == "posix":
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            return
        except (ProcessLookupError, PermissionError, OSError):
            pass
    try:
        proc.kill()
    except ProcessLookupError:
        pass


async def _run(config: ServerConfig, argv: Sequence[str], *,
               on_event: EventHook | None = None) -> CommandResult:
    if on_event is not None:
        await on_event("council started")
    kwargs: dict[str, Any] = {
        "stdin": asyncio.subprocess.DEVNULL,
        "stdout": asyncio.subprocess.PIPE,
        "stderr": asyncio.subprocess.PIPE,
        "env": _child_env(),
    }
    if os.name == "posix":
        kwargs["start_new_session"] = True
    try:
        proc = await asyncio.create_subprocess_exec(*argv, **kwargs)
    except (OSError, ValueError) as exc:
        raise CouncilError(f"cannot start council: {exc}") from exc

    try:
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(),
                                                     timeout=config.timeout)
        except TimeoutError:
            _kill(proc)
            await proc.wait()
            raise CouncilError(
                f"council did not finish within {config.timeout:g}s")
        except asyncio.CancelledError:
            _kill(proc)
            await proc.wait()
            raise
    finally:
        if proc.returncode is None:
            _kill(proc)
            await proc.wait()

    err = stderr.decode("utf-8", "replace")
    if proc.returncode == 3:
        detail = err.strip().splitlines()
        raise CouncilError(detail[-1] if detail else "council could not start")
    if proc.returncode not in (0, 1, 2):
        detail = err.strip().splitlines()
        raise CouncilError(detail[-1] if detail else
                           f"council exited {proc.returncode}")
    try:
        payload = json.loads(stdout.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CouncilError("council did not print a JSON result") from exc
    if on_event is not None:
        await on_event("council finished")
    return CommandResult(payload, proc.returncode, err)


async def run_plan(config: ServerConfig, options: ReviewOptions, *,
                   on_event: EventHook | None = None) -> CommandResult:
    """Run `council review --plan --json`; no reviewer and no run directory."""
    repo = _resolve_repo(config, options.repo)
    argv = [*_base_command(config), "review", "--json", "--plan", "-C", str(repo)]
    _append_review_args(config, options, argv)
    return await _run(config, argv, on_event=on_event)


async def run_review(config: ServerConfig, options: ReviewOptions, *,
                     on_event: EventHook | None = None) -> CommandResult:
    """Run a real gate review and retain its evidence outside the repository."""
    repo = _resolve_repo(config, options.repo)
    run_id = uuid4().hex
    keep = config.state_root
    try:
        keep.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise CouncilError(f"cannot create the evidence directory {keep}: {exc}") from exc

    argv = [*_base_command(config), "review", "--json", "-C", str(repo),
            "--run-id", run_id, "--keep", str(keep), "--autonomous"]
    _append_review_args(config, options, argv)
    result = await _run(config, argv, on_event=on_event)
    return replace(result, run_dir=keep / run_id)


async def run_doctor(config: ServerConfig, *,
                     on_event: EventHook | None = None) -> CommandResult:
    """Run `council doctor --json`; no repository and no review."""
    argv = [*_base_command(config), "doctor", "--json",
            "--agent", config.agent]
    if config.profile:
        argv.extend(["--profile", config.profile])
    if config.reviewer:
        argv.extend(["--reviewer", config.reviewer])
    return await _run(config, argv, on_event=on_event)


def _positive_float(raw: str) -> float:
    value = float(raw)
    if value <= 0:
        raise ValueError("timeout must be positive")
    return value


def add_server_arguments(parser: Any) -> None:
    """Options shared by `council-mcp` and `council-acp`.

    These are deployment options, not protocol inputs. In particular the
    reviewer executable is never chosen by a remote MCP client.
    """
    parser.add_argument("--repo-root", type=Path, default=Path.cwd(), metavar="DIR",
                        help="only repositories beneath DIR may be reviewed")
    parser.add_argument("--state-root", type=Path, default=default_state_root(),
                        metavar="DIR", help="where retained evidence is written")
    parser.add_argument("--reviewer", default=None,
                        help="executable for the selected adapter (default: adapter's default)")
    parser.add_argument("--agent", default="hermes",
                        help="reviewer adapter (default: hermes)")
    parser.add_argument("--profile", default=None,
                        help="profile for an adapter that uses one (Hermes)")
    parser.add_argument("--no-sandbox", action="store_true",
                        help="pass --no-sandbox to council")
    parser.add_argument("--timeout", type=_positive_float, default=3600.0,
                        metavar="SECONDS", help="whole review process timeout")
    parser.add_argument("--council", default=None,
                        help="council executable (default: PATH, then python -m council)")


def config_from_args(args: Any) -> ServerConfig:
    root = local_path(args.repo_root).expanduser()
    if not root.is_dir():
        raise SystemExit(f"--repo-root is not a directory: {root}")
    command = (args.council,) if args.council else ()
    return ServerConfig(root=root.resolve(), state_root=local_path(args.state_root),
                        agent=args.agent, reviewer=args.reviewer, profile=args.profile,
                        no_sandbox=bool(args.no_sandbox), timeout=float(args.timeout),
                        command=command)
