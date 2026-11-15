"""Caller-owned path scope: a pure decision over diff paths.

A scope is not repository configuration. The repository being reviewed cannot
choose what is reviewed; only the caller can. The decision is deliberately
small: an exclude wins, an include that matches nothing is a failure rather
than an empty review, and a dropped path is named rather than forgotten.
"""

from __future__ import annotations

from dataclasses import dataclass
from fnmatch import fnmatchcase

from ..changes import file_sections
from .text import printable


class ScopeError(ValueError):
    """A scope pattern is not a usable repository-relative glob."""


@dataclass(frozen=True, slots=True)
class ScopeIgnored:
    """A changed path the caller's scope kept out of the review."""

    path: str
    reason: str
    pattern: str | None = None


@dataclass(frozen=True, slots=True)
class ScopeDecision:
    """Whether one path is reviewed, and why."""

    included: bool
    reason: str
    pattern: str | None = None


def _validate(pattern: str) -> None:
    if not isinstance(pattern, str) or not pattern:
        raise ScopeError("a scope pattern must not be empty")
    if pattern != pattern.strip():
        raise ScopeError(f"scope pattern {pattern!r} has surrounding whitespace")
    if len(pattern) > 512:
        raise ScopeError(f"scope pattern {pattern!r} is longer than 512 characters")
    if pattern.startswith(("/", "\\")):
        raise ScopeError(f"scope pattern {pattern!r} must be repository-relative")
    if "\\" in pattern:
        raise ScopeError(f"scope pattern {pattern!r} must use / as the separator")
    if not printable(pattern):
        raise ScopeError(f"scope pattern {pattern!r} contains a control character")
    parts = pattern.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise ScopeError(f"scope pattern {pattern!r} has an empty or relative segment")


def _match(pattern: str, path: str) -> bool:
    """Git-style matching: `*` stays in one segment, a `**` segment recurses."""
    pattern_parts = pattern.split("/")
    path_parts = path.split("/")

    def walk(pattern_index: int, path_index: int) -> bool:
        if pattern_index == len(pattern_parts):
            return path_index == len(path_parts)
        part = pattern_parts[pattern_index]
        if part == "**":
            return any(walk(pattern_index + 1, candidate)
                       for candidate in range(path_index, len(path_parts) + 1))
        return (path_index < len(path_parts)
                and fnmatchcase(path_parts[path_index], part)
                and walk(pattern_index + 1, path_index + 1))

    return walk(0, 0)


def _first_match(patterns: tuple[str, ...], path: str) -> str | None:
    return next((pattern for pattern in patterns if _match(pattern, path)), None)


@dataclass(frozen=True, slots=True)
class Scope:
    """A validated include/exclude policy. Empty include means every path."""

    includes: tuple[str, ...] = ()
    excludes: tuple[str, ...] = ()

    @classmethod
    def create(cls, includes: tuple[str, ...] = (),
               excludes: tuple[str, ...] = ()) -> Scope:
        for pattern in (*includes, *excludes):
            _validate(pattern)
        return cls(tuple(includes), tuple(excludes))

    def decide(self, path: str) -> ScopeDecision:
        excluded = _first_match(self.excludes, path)
        if excluded is not None:
            return ScopeDecision(False, "excluded", excluded)
        if self.includes:
            included = _first_match(self.includes, path)
            if included is None:
                return ScopeDecision(False, "outside include")
            return ScopeDecision(True, "included", included)
        return ScopeDecision(True, "included")

    def keeps(self, path: str) -> bool:
        return self.decide(path).included

    def filter_patch(self, patch: str) -> tuple[str, tuple[ScopeIgnored, ...]]:
        """Keep included file sections and name every section that was dropped."""
        kept: list[str] = []
        ignored: list[ScopeIgnored] = []
        for section in file_sections(patch):
            decision = self.decide(section.path)
            if decision.included:
                kept.append(section.text)
            else:
                ignored.append(ScopeIgnored(section.path, decision.reason,
                                            decision.pattern))
        return "".join(kept), tuple(ignored)
