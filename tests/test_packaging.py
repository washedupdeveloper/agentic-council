"""The package states one version and ships the instrument it reviews with."""

from __future__ import annotations

import tomllib
from pathlib import Path

from council.run import default_prompt

ROOT = Path(__file__).resolve().parent.parent


def project() -> dict[str, object]:
    return tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]


def test_the_package_version_is_the_released_version() -> None:
    version = str(project()["version"])
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert f"## [{version}]" in changelog


def test_the_reviewer_prompt_ships_with_the_package() -> None:
    prompt = default_prompt()
    assert prompt.is_file()
    assert "sections" in prompt.read_text(encoding="utf-8")


def test_both_console_scripts_are_declared() -> None:
    assert project()["scripts"] == {
        "council": "council.cli:main",
        "council-verify": "council.claims:main",
    }
