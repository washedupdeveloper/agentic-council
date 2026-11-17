"""MCP adapter package; import failure is a deliberate, actionable error."""

from __future__ import annotations

import sys


def main() -> int:
    try:
        from .server import main as run
    except ModuleNotFoundError as exc:
        if exc.name == "mcp":
            print("council-mcp: MCP support is not installed; "
                  "install 'council[mcp]' or 'council[mcp,acp]'", file=sys.stderr)
            return 3
        raise
    return run()


__all__ = ["main"]
