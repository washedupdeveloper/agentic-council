"""The shared vocabulary: dimensions, severities, proof kinds.

Both the prompt contract (`council.prompt`) and the parser contract
(`council.schema`) depend on these names, but neither depends on the other.
"""

from __future__ import annotations

from .findings import SEVERITIES as SEVERITIES  # noqa: PLC0414 - re-exported vocabulary

DIMENSIONS: tuple[str, ...] = (
    "security",
    "correctness",
    "readability",
    "architecture",
    "performance",
)
PROOF_KINDS: tuple[str, ...] = ("absent", "present", "command", "json", "diff")
