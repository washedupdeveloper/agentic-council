"""council — a review is a claim until a check settles it.

The domain is two types: a `Finding` (a claim plus the state its evidence
reached) and a `Result` (what those states mean for the run). Everything else
in the package exists to produce those two.
"""

__all__ = ["findings", "verdict"]
try:
    from importlib.metadata import PackageNotFoundError
    from importlib.metadata import version as _distribution_version

    __version__ = _distribution_version("council")
except PackageNotFoundError:  # a source checkout, not an installed distribution
    __version__ = "0.0.0+source"
