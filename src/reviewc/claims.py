"""The claim registry: every claim this project makes is a command that fails.

A claim that lives only in prose is a claim nobody checks. Each entry in
`claims.toml` names one sentence and the command that would falsify it; `verify`
runs them all and exits non-zero if any is false, so the documentation and the
tree cannot disagree for longer than one run.

The registry is also the source for the generated table in `docs/CLAIMS.md`, so
a new claim cannot be added to the docs without a check to back it.
"""

from __future__ import annotations

import shlex
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path

DEFAULT_REGISTRY = Path("claims.toml")
DEFAULT_TIMEOUT = 900


@dataclass(frozen=True, slots=True)
class Claim:
    """One sentence this project asserts, and the command that proves it."""

    id: str
    text: str
    check: str


@dataclass(frozen=True, slots=True)
class ClaimResult:
    claim: Claim
    ok: bool
    detail: str


class RegistryError(ValueError):
    """The registry itself is malformed; nothing should run."""


def load(path: Path) -> list[Claim]:
    """Read and validate the registry. Every problem is reported at once."""
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise RegistryError(f"cannot read {path}: {exc}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise RegistryError(f"{path} is not valid TOML: {exc}") from exc

    entries = raw.get("claim")
    if not isinstance(entries, list) or not entries:
        raise RegistryError(f"{path} declares no [[claim]] entries")

    claims: list[Claim] = []
    problems: list[str] = []
    seen: set[str] = set()
    for index, entry in enumerate(entries, start=1):
        if not isinstance(entry, dict):
            problems.append(f"claim #{index} is not a table")
            continue
        ident = entry.get("id")
        text = entry.get("text")
        check = entry.get("check")
        missing = [k for k, v in (("id", ident), ("text", text), ("check", check))
                   if not isinstance(v, str) or not v.strip()]
        if missing:
            problems.append(f"claim #{index} is missing {', '.join(missing)}")
            continue
        assert isinstance(ident, str) and isinstance(text, str) and isinstance(check, str)
        if ident in seen:
            problems.append(f"duplicate claim id {ident!r}")
            continue
        seen.add(ident)
        if not text.rstrip().endswith("."):
            problems.append(f"{ident}: the text is a sentence, end it with a period")
        claims.append(Claim(ident, text, check))

    if problems:
        raise RegistryError(f"{path}:\n  - " + "\n  - ".join(problems))
    return claims


def run_one(claim: Claim, cwd: Path, timeout: int = DEFAULT_TIMEOUT) -> ClaimResult:
    """Run one claim's check. A timeout is a failure, not a pass."""
    argv = shlex.split(claim.check)
    if not argv:
        return ClaimResult(claim, False, "empty check")
    try:
        proc = subprocess.run(argv, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError:
        return ClaimResult(claim, False, f"check command not found: {argv[0]}")
    except subprocess.TimeoutExpired:
        return ClaimResult(claim, False, f"check timed out after {timeout}s")

    ok = proc.returncode == 0
    if ok:
        return ClaimResult(claim, True, "")
    tail = (proc.stderr or proc.stdout).strip().splitlines()
    return ClaimResult(claim, False, f"exit {proc.returncode}: {tail[-1] if tail else ''}".rstrip())


def run_all(claims: list[Claim], cwd: Path, timeout: int = DEFAULT_TIMEOUT) -> list[ClaimResult]:
    """Run every claim, in registry order, and keep going after a failure."""
    return [run_one(claim, cwd, timeout) for claim in claims]


def main(argv: list[str] | None = None) -> int:
    """`python -m reviewc.claims [--registry PATH] [--list]`."""
    args = list(sys.argv[1:] if argv is None else argv)
    registry = DEFAULT_REGISTRY
    if "--registry" in args:
        registry = Path(args[args.index("--registry") + 1])
    try:
        claims = load(registry)
    except RegistryError as exc:
        print(f"claims: {exc}", file=sys.stderr)
        return 2

    if "--list" in args:
        for claim in claims:
            print(f"{claim.id}\t{claim.text}")
        return 0

    results = run_all(claims, Path.cwd())
    failed = [r for r in results if not r.ok]
    for result in results:
        mark = "ok  " if result.ok else "FAIL"
        print(f"  {mark} {result.claim.id}: {result.claim.text}")
        if not result.ok:
            print(f"       {result.detail}")
    print(f"\n{len(results) - len(failed)}/{len(results)} claims hold")
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())