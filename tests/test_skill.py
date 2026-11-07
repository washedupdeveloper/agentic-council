"""The skill is documentation an agent follows, so its commands must exist."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from council import cli

SKILL = Path(__file__).resolve().parent.parent / "skills" / "council" / "SKILL.md"


def test_the_skill_has_frontmatter() -> None:
    text = SKILL.read_text(encoding="utf-8")
    assert text.startswith("---")
    assert "name: council" in text
    assert "description: Use when" in text


def test_every_command_the_skill_names_exists() -> None:
    text = SKILL.read_text(encoding="utf-8")
    verbs = {match.group(1) for match in re.finditer(r"\bcouncil ([a-z]+)", text)}
    assert verbs, "the skill names no command"
    for verb in verbs:
        with pytest.raises(SystemExit) as raised:
            cli.main([verb, "--help"])
        assert raised.value.code == 0, verb


def test_the_skill_does_not_promise_a_score() -> None:
    text = SKILL.read_text(encoding="utf-8").lower()
    assert "no score" in text
    assert "threshold" in text
