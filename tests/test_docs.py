"""Every flag the CLI accepts is documented, and every command it offers."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from council.cli import build_parser

README = Path(__file__).resolve().parent.parent / "README.md"
MUTATION_TOOL = Path(__file__).resolve().parent.parent / "tools" / "mutation_check.py"


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
    parser = build_parser()
    subcommands = next(
        action for action in parser._actions  # noqa: SLF001
        if isinstance(action, argparse._SubParsersAction)  # noqa: SLF001
    )
    missing = [name for name in subcommands.choices if f"council {name}" not in text]
    assert not missing, f"undocumented command(s): {', '.join(missing)}"


def test_the_repository_configuration_is_documented() -> None:
    """A security-relevant knob that exists only in code is a trap."""
    text = README.read_text(encoding="utf-8")
    assert "## Configuration" in text
    assert "council.toml" in text
    assert "[proofs]" in text


def test_every_mutation_flag_is_documented() -> None:
    """The campaign's flags are a surface too, and the CLI walk never reaches them.

    `options(build_parser())` walks `council.cli`; `tools/mutation_check.py` builds its
    own parser, so `--shard` and `--jobs` could be added, printed in `--help`, and absent
    from every page a user reads. A flag a user can type but cannot look up is a trap.
    """
    # Declarations only. The tool also hands pytest its own arguments, and a quoted
    # `--no-header` inside that argv is not a flag this tool offers anyone.
    flags = set(
        re.findall(
            r'add_argument\(\s*"(--[a-z][a-z-]*)"',
            MUTATION_TOOL.read_text(encoding="utf-8"),
            re.S,
        )
    )
    text = README.read_text(encoding="utf-8")
    missing = sorted(flag for flag in flags if flag not in text)
    assert not missing, f"undocumented mutation flag(s): {', '.join(missing)}"
