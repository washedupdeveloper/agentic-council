"""`council.toml`: the few things a repository is allowed to decide.

A key that does nothing is a lie, so unknown keys are refused rather than
ignored — a misspelt `allow` that silently falls back to the default would look
exactly like a working allowlist.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

CONFIG_NAME = "council.toml"

#: Read-only inspection tools, plus the two that can evaluate the repository it
#: is already reviewing. This is an allowlist against surprise, not a sandbox:
#: `nix` can run anything the flake says, and the flake is the code under review.
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