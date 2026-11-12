"""Pure identity of a proof list."""

from __future__ import annotations

import json
from typing import Any, Mapping, Sequence


def canonical_proof(proofs: Sequence[tuple[str, Mapping[str, Any]]]) -> str:
    """A stable text identity for the proof list, independent of dict order."""
    items = [[kind, dict(params)] for kind, params in proofs]
    return json.dumps(items, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, default=str)
