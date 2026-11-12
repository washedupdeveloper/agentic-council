"""Pure domain kernel: decisions that can be tested with literals.

Nothing in this package may import an adapter or touch the world. The effect
shell is `council.cli`, `council.run`, `council.adjudicate`, `council.base`,
`council.repo`, `council.runner`, `council.proofs`, `council.pr`,
`council.doctor`, `council.config`, `council.sample`, `council.paths`,
`council.sandbox`, `council.reference`, `council.version` and `council.claims`.
"""

from __future__ import annotations

__all__ = ["adjudication", "config", "run_id", "sandbox"]
