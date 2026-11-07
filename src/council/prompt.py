"""The prompt ships in the package; the digest covers template, profile and
dimensions, so runs of different instruments are never averaged."""

from __future__ import annotations

import hashlib
from typing import Sequence

from .schema import DIMENSIONS

BASE = "{{base}}"
DIFF = "{{diff}}"


class PromptError(ValueError):
    """The template is not usable."""


def render(template: str, *, base: str, diff: str) -> str:
    """Fill the template. A template missing a placeholder is an error, not a surprise."""
    missing = [name for name in (BASE, DIFF) if name not in template]
    if missing:
        raise PromptError(f"the prompt template is missing {', '.join(missing)}")
    return template.replace(BASE, base).replace(DIFF, diff)


def instrument_digest(template: str, *, profile: str,
                      dimensions: Sequence[str] = DIMENSIONS) -> str:
    """A short hash of everything that decides what a sample means.

    Deliberately excludes the diff: the digest identifies the instrument, so two
    runs over different changes share it, and a prompt or profile change breaks
    it.
    """
    digest = hashlib.sha256()
    for part in ("reviewc-prompt-v1", template, profile, *dimensions):
        digest.update(part.encode("utf-8"))
        digest.update(b"\x00")
    return digest.hexdigest()[:16]