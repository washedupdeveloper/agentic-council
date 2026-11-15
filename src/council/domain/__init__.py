"""Pure domain kernel: decisions that can be tested with literals.

Nothing in this package may import an adapter or touch the world. The effect
shell is `council.cli`, `council.run`, `council.adjudicate`, `council.base`,
`council.baseline`, `council.repo`, `council.runner`, `council.proofs`,
`council.pr`, `council.doctor`, `council.config`, `council.sample`,
`council.paths`, `council.sandbox`, `council.reference`, `council.version` and
`council.claims`.
"""

from __future__ import annotations

# Names are imported explicitly by their consumers; this is a namespace marker,
# not a re-export surface. Keeping a stale __all__ here made `proof` look public
# after the module was removed.
