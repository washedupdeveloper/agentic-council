"""reviewc — a review is a claim until a check settles it.

The domain is two types: a `Finding` (a claim plus the state its evidence
reached) and a `Result` (what those states mean for the run). Everything else
in the package exists to produce those two.
"""

__all__ = ["findings", "verdict"]
__version__ = "0.1.0"