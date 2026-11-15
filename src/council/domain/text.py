"""Printable-text rules, shared by terminal output and input validation."""

from __future__ import annotations

import unicodedata

_FORBIDDEN = frozenset({"Cc", "Cf", "Cs", "Zl", "Zp"})


def sanitize(text: object) -> str:
    """One printable line: control and directionality characters become spaces."""
    return "".join(ch if unicodedata.category(ch) not in _FORBIDDEN else " "
                   for ch in str(text))


def printable(text: str) -> bool:
    """Whether every character is safe to print on one line."""
    return all(unicodedata.category(ch) not in _FORBIDDEN for ch in text)
