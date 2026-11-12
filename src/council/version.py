"""Installed distribution version lookup.

The package import must not read metadata; this adapter answers only when a
caller asks. A source checkout falls back to the same string as
`council.__version__`.
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

SOURCE_VERSION = "0.0.0+source"


def current_version() -> str:
    """The installed version, or the source fallback outside a distribution."""
    try:
        return version("council")
    except PackageNotFoundError:
        return SOURCE_VERSION
