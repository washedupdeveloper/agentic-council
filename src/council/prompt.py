"""The prompt ships in the package; the digest covers template, profile and
dimensions, so runs of different instruments are never averaged."""

from __future__ import annotations

import hashlib
from typing import Sequence

from .schema import DIMENSIONS, PROOF_KINDS, SEVERITIES

#: The rule a sample was asked under. A prompt change and a contract change are
#: both instrument changes, so both break the digest.
CONTRACT = "|".join((*SEVERITIES, *PROOF_KINDS))

BASE = "{{base}}"
DIFF = "{{diff}}"
CONTEXT = "{{context}}"


class PromptError(ValueError):
    """The template is not usable."""


def render(template: str, *, base: str, diff: str, context: str = "") -> str:
    """Fill the template. A template missing a placeholder is an error, not a surprise.

    `{{context}}` is optional: a prompt that does not ask for the surrounding
    functions is not silently given them.
    """
    missing = [name for name in (BASE, DIFF) if name not in template]
    if missing:
        raise PromptError(f"the prompt template is missing {', '.join(missing)}")
    text = template.replace(BASE, base).replace(DIFF, diff)
    return text.replace(CONTEXT, context) if CONTEXT in template else text


def instrument_digest(template: str, *, profile: str,
                      dimensions: Sequence[str] = DIMENSIONS,
                      contract: str = CONTRACT) -> str:
    """A short hash of everything that decides what a sample means.

    Deliberately excludes the diff: the digest identifies the instrument, so two
    runs over different changes share it, and a prompt or profile change breaks
    it.
    """
    digest = hashlib.sha256()
    for part in ("council-prompt-v2", contract, template, profile, *dimensions):
        digest.update(part.encode("utf-8"))
        digest.update(b"\x00")
    return digest.hexdigest()[:16]