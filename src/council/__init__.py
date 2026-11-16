"""council — a review is a claim until a check settles it.

The domain is two types: `Finding` (a claim and the state its evidence reached)
and `Result` (what those states mean). Importing the package performs no I/O:
`__version__` is resolved on access.
"""

from __future__ import annotations

from . import findings, verdict

__all__ = ["findings", "verdict"]


def __getattr__(name: str) -> str:
    """Resolve `__version__` on access, not at import time."""
    if name == "__version__":
        from .version import current_version

        return current_version()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
