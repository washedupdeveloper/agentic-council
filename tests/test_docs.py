"""Every flag the CLI accepts is documented, and every command it offers."""

from __future__ import annotations

import argparse
from pathlib import Path

from council.cli import build_parser

README = Path(__file__).resolve().parent.parent / "README.md"


def options(parser: argparse.ArgumentParser) -> list[str]:
    """Every option string, including the subcommands' own parsers."""
    found: list[str] = []
    for action in parser._actions:  # noqa: SLF001 - argparse exposes no public walker
        found.extend(action.option_strings)
        if isinstance(action, argparse._SubParsersAction):  # noqa: SLF001
            for sub in action.choices.values():
                found.extend(options(sub))
    return found


def test_every_flag_is_documented() -> None:
    """A flag a user can type but cannot look up is a trap, not a feature."""
    text = README.read_text(encoding="utf-8")
    missing = sorted({option for option in options(build_parser()) if option not in text})
    assert not missing, f"undocumented flag(s): {', '.join(missing)}"


def test_every_command_is_documented() -> None:
    text = README.read_text(encoding="utf-8")
    missing = [name for name in ("review", "verify", "init") if f"council {name}" not in text]
    assert not missing, f"undocumented command(s): {', '.join(missing)}"