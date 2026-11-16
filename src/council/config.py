"""Load `council.toml` from disk and hand its text to the pure parser.

This module is the effect shell: it checks the path, reads bytes and decodes
UTF-8. Every decision about what the configuration *means* is in
`council.domain.config`.
"""

from __future__ import annotations

from pathlib import Path

from .domain.config import (
    CONFIG_NAME,
    DEFAULT_ALLOW,
    DEFAULT_POLICY,
    RULE_BYTES,
    Config,
    ConfigError,
    Policy,
    Rule,
    parse,
)

__all__ = [
    "CONFIG_NAME", "DEFAULT_ALLOW", "DEFAULT_POLICY", "RULE_BYTES", "Config",
    "ConfigError", "Policy", "Rule", "load",
]


def load(path: Path, policy: Policy = DEFAULT_POLICY) -> Config:
    """Load `council.toml`; a missing file means the policy, an unknown key is an error."""
    try:
        if path.is_symlink():
            if not path.exists():
                raise ConfigError(f"{path} is a broken symlink")
            raise ConfigError(f"{path} is a symlink: configuration must be a regular file")
        if not path.exists():
            return Config(allow=policy.allow, timeout=policy.timeout,
                          sandbox=policy.sandbox, rules=())
        if not path.is_file():
            raise ConfigError(f"{path} is not a regular file")
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigError(f"cannot read {path}: {exc}") from exc
    except UnicodeDecodeError as exc:
        raise ConfigError(f"{path} is not UTF-8 text") from exc
    return parse(text, name=path.name, policy=policy)
