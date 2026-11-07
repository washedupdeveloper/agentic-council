"""`council.toml`: `[proofs].allow` and `timeout`. Unknown keys are refused, so
a typo cannot silently restore the default allowlist."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

CONFIG_NAME = "council.toml"

#: The tools this repository trusts a proof to run. Not a boundary: `nix` builds
#: and `python3` executes, so anything here can run repository code with your
#: rights. A real boundary is a sandbox; this is a list of known tools, and
#: removing one interpreter closes a spelling, not the hole.
DEFAULT_ALLOW: frozenset[str] = frozenset(
    {"rg", "grep", "git", "jq", "test", "stat", "python3", "nix"}
)


class ConfigError(ValueError):
    """The configuration says something the tool will not do."""


@dataclass(frozen=True, slots=True)
class Config:
    allow: frozenset[str] = DEFAULT_ALLOW
    timeout: int = 120


def load(path: Path) -> Config:
    """Load `council.toml`; a missing file means the defaults, an unknown key is an error."""
    if not path.exists():
        return Config()
    raw = tomllib.loads(path.read_text(encoding="utf-8"))

    unknown = set(raw) - {"proofs"}
    if unknown:
        raise ConfigError(f"unknown key(s) in {path.name}: {', '.join(sorted(unknown))}")

    proofs = raw.get("proofs", {})
    if not isinstance(proofs, dict):
        raise ConfigError("[proofs] must be a table")
    unknown = set(proofs) - {"allow", "timeout"}
    if unknown:
        raise ConfigError(f"unknown key(s) in [proofs]: {', '.join(sorted(unknown))}")

    allow_raw = proofs.get("allow")
    if allow_raw is None:
        allow = DEFAULT_ALLOW
    else:
        if not isinstance(allow_raw, list) or not all(isinstance(x, str) and x for x in allow_raw):
            raise ConfigError("[proofs].allow must be a list of executable names")
        allow = frozenset(allow_raw)

    timeout = proofs.get("timeout", 120)
    if not isinstance(timeout, int) or timeout < 1:
        raise ConfigError("[proofs].timeout must be a positive integer")

    return Config(allow=allow, timeout=timeout)