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


def test_the_package_ships_a_typed_marker() -> None:
    import council

    assert (Path(council.__file__).resolve().parent / "py.typed").is_file()


def test_the_console_scripts_are_declared() -> None:
    assert project()["scripts"] == {
        "council": "council.cli:main",
        "council-verify": "council.claims:main",
        "council-mcp": "council_mcp:main",
        "council-acp": "council_acp:main",
    }


def test_the_protocol_adapters_are_optional_extras() -> None:
    extras = project()["optional-dependencies"]
    assert "mcp" in extras
    assert "acp" in extras
    assert "server" in extras
    assert any(dep.startswith("mcp") for dep in extras["mcp"])
    assert any(dep.startswith("agent-client-protocol") for dep in extras["acp"])
