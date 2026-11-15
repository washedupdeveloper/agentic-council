"""council — a review is a claim until a check settles it.

The domain is two types: a `Finding` (a claim plus the state its evidence
reached) and a `Result` (what those states mean for the run). Everything else
in the package exists to produce those two.

Importing this package performs no I/O. The installed version is resolved
lazily by `council.version.current_version`; reading `council.__version__` is
what asks for it.
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
