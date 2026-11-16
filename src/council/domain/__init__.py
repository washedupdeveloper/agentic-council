"""Pure domain kernel: decisions that can be tested with literals.

Nothing here may import an adapter or touch the world. The adapters are declared
in `tests/test_architecture.py`, which fails when a new effectful module is not.
"""

from __future__ import annotations

# Names are imported explicitly by their consumers; this is a namespace marker,
# not a re-export surface. Keeping a stale __all__ here made `proof` look public
# after the module was removed.
