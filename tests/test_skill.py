"""The skill is documentation an agent follows, so its declarations must be true.

Every claim the skill makes about the CLI is declared in its frontmatter and
checked here in both directions: a flag the body names must exist, a subcommand
the parser offers must be declared, an artefact the skill promises must be named
where an agent will look for it. A skill that drifts from the tool is a skill
that teaches an agent to assume.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from council import cli

SKILL = Path(__file__).resolve().parent.parent / "skills" / "council" / "SKILL.md"

_FRONTMATTER = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)
_FLAG = re.compile(r"--[a-z][a-z0-9-]+")


def text() -> str:
    return SKILL.read_text(encoding="utf-8")


def body() -> str:
    match = _FRONTMATTER.match(text())
    assert match is not None, "the skill has no frontmatter"
    return text()[match.end():]


def declared() -> dict[str, list[str]]:
    """The `key: [a, b, c]` lists in the frontmatter, parsed without a YAML dep."""
    match = _FRONTMATTER.match(text())
    assert match is not None, "the skill has no frontmatter"
    found: dict[str, list[str]] = {}
    for line in match.group(1).splitlines():
        key, _, value = line.partition(":")
        value = value.strip()
        if not (value.startswith("[") and value.endswith("]")):
            continue
        found[key.strip()] = [item.strip() for item in value[1:-1].split(",") if item.strip()]
    return found


def test_the_skill_has_frontmatter() -> None:
    assert text().startswith("---")
    assert "name: council" in text()
    assert "description: Use when" in text()


def test_every_declared_command_exists() -> None:
    commands = declared()["commands"]
    assert commands, "the skill declares no commands"
    for command in commands:
        with pytest.raises(SystemExit) as raised:
            cli.main([command, "--help"])
        assert raised.value.code == 0, command


def test_every_command_the_parser_offers_is_declared() -> None:
    """A new subcommand that the skill does not declare is a skill that lies."""
    import argparse

    from council.cli import build_parser

    parser = build_parser()
    subcommands = next(
        action for action in parser._actions  # noqa: SLF001 - argparse has no public walker
        if isinstance(action, argparse._SubParsersAction)  # noqa: SLF001
    )
    assert set(subcommands.choices) == set(declared()["commands"])


def test_every_declared_flag_exists() -> None:
    import argparse

    from council.cli import build_parser

    def options(parser: argparse.ArgumentParser) -> set[str]:
        found: set[str] = set()
        for action in parser._actions:  # noqa: SLF001
            found.update(action.option_strings)
            if isinstance(action, argparse._SubParsersAction):  # noqa: SLF001
                for sub in action.choices.values():
                    found.update(options(sub))
        return found

    available = options(build_parser())
    unknown = sorted(set(declared()["flags"]) - available)
    assert not unknown, f"the skill declares flag(s) the CLI does not accept: {unknown}"


def test_every_flag_the_body_names_is_declared() -> None:
    named = set(_FLAG.findall(body()))
    undeclared = sorted(named - set(declared()["flags"]))
    assert not undeclared, f"the body names undeclared flag(s): {undeclared}"


def test_every_declared_artefact_is_named_in_the_body() -> None:
    missing = [item for item in declared()["artefacts"] if item not in body()]
    assert not missing, f"the skill promises artefact(s) it never explains: {missing}"


def test_the_skill_does_not_promise_a_score() -> None:
    lower = text().lower()
    assert "no score" in lower
    assert "threshold" in lower
