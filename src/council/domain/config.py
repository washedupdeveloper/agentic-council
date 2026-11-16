"""Pure configuration decisions.

Text in, `Config` out. The file system lives in `council.config.load`; this
module never opens, stats or writes anything.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass

CONFIG_NAME = "council.toml"

#: The tools this repository trusts a proof to name. `command` proofs are
#: sandboxed (see `sandbox.py`); this list decides which tools may be named at
#: all, and is a convenience filter rather than a boundary.
DEFAULT_ALLOW: frozenset[str] = frozenset(
    {"rg", "grep", "git", "jq", "test", "stat", "python3", "nix"}
)


class ConfigError(ValueError):
    """The configuration says something the tool will not do."""


@dataclass(frozen=True, slots=True)
class Policy:
    """What the caller permits. A repository may narrow this, never widen it.

    The repository is untrusted input: it can ask for less than the caller
    allows, but it cannot add a binary, raise the timeout, or turn the sandbox
    off when the caller requires it.
    """

    allow: frozenset[str] = DEFAULT_ALLOW
    timeout: int = 120
    sandbox: bool = True


DEFAULT_POLICY = Policy()


@dataclass(frozen=True, slots=True)
class Rule:
    """One path glob and the document that governs it.

    Both are repository-relative POSIX paths, and both are checked: a rule may
    not read outside the checkout, and it may not name a directory.
    """

    glob: str
    doc: str


#: How much of a rule's document reaches the prompt. A repository cannot make
#: the prompt unbounded by pointing a rule at a large file; a document that is
#: cut is recorded as truncated rather than silently shortened.
RULE_BYTES = 20000


@dataclass(frozen=True, slots=True)
class Config:
    allow: frozenset[str] = DEFAULT_ALLOW
    timeout: int = 120
    sandbox: bool = True
    rules: tuple[Rule, ...] = ()


def parse(text: str, *, name: str = CONFIG_NAME,
          policy: Policy = DEFAULT_POLICY) -> Config:
    """Parse `council.toml` text. Pure: no path, no environment, no default file."""
    try:
        raw = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"{name} is not valid TOML: {exc}") from exc

    unknown = set(raw) - {"proofs", "rules"}
    if unknown:
        raise ConfigError(f"unknown key(s) in {name}: {', '.join(sorted(unknown))}")

    rules = _parse_rules(raw.get("rules", []), name)

    proofs = raw.get("proofs", {})
    if not isinstance(proofs, dict):
        raise ConfigError("[proofs] must be a table")
    unknown = set(proofs) - {"allow", "timeout", "sandbox"}
    if unknown:
        raise ConfigError(f"unknown key(s) in [proofs]: {', '.join(sorted(unknown))}")

    allow_raw = proofs.get("allow")
    if allow_raw is None:
        allow = policy.allow
    else:
        if not isinstance(allow_raw, list) or not all(
                isinstance(x, str) and x for x in allow_raw):
            raise ConfigError("[proofs].allow must be a list of executable names")
        requested = frozenset(allow_raw)
        extra = requested - policy.allow
        if extra:
            raise ConfigError(
                "[proofs].allow names " + ", ".join(sorted(extra))
                + ", which this runner does not permit")
        allow = requested

    timeout = proofs.get("timeout", policy.timeout)
    if isinstance(timeout, bool) or not isinstance(timeout, int) or timeout < 1:
        raise ConfigError("[proofs].timeout must be a positive integer")
    timeout = min(timeout, policy.timeout)

    sandbox = proofs.get("sandbox", policy.sandbox)
    if not isinstance(sandbox, bool):
        raise ConfigError("[proofs].sandbox must be true or false")
    if not sandbox and policy.sandbox:
        raise ConfigError(
            "[proofs].sandbox = false, but this runner requires the sandbox")

    return Config(allow=allow, timeout=timeout, sandbox=policy.sandbox or sandbox,
                  rules=rules)


def _parse_rules(raw: object, name: str) -> tuple[Rule, ...]:
    """`[[rules]]` entries: a glob and the document that governs what it matches."""
    if not isinstance(raw, list):
        raise ConfigError(f"[[rules]] in {name} must be an array of tables")
    rules: list[Rule] = []
    for index, entry in enumerate(raw, start=1):
        if not isinstance(entry, dict):
            raise ConfigError(f"[[rules]] entry {index} in {name} must be a table")
        unknown = set(entry) - {"glob", "doc"}
        if unknown:
            raise ConfigError(
                f"unknown key(s) in [[rules]] entry {index} of {name}: "
                f"{', '.join(sorted(unknown))}")
        values: dict[str, str] = {}
        for key in ("glob", "doc"):
            value = entry.get(key)
            if not isinstance(value, str) or not value:
                raise ConfigError(
                    f"[[rules]] entry {index} in {name} needs a non-empty {key}")
            if value.startswith("/") or "\\" in value or ".." in value.split("/"):
                raise ConfigError(
                    f"[[rules]] entry {index} in {name}: {key} {value!r} must be a "
                    "repository-relative POSIX path")
            values[key] = value
        rules.append(Rule(values["glob"], values["doc"]))
    return tuple(rules)
