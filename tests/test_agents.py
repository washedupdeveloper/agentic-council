"""The adapter seam: built-in Hermes, and an extension that needs no core edit."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

import council.cli as cli
from council.agents import (
    AgentIdentity,
    AgentOptions,
    AgentRegistry,
    BUILTIN,
    resolve,
    register,
    unregister,
)
from council.domain.schema import DIMENSIONS
from council.run import ReviewRequest, review


class ExampleAdapter:
    """A deliberately tiny second adapter for the seam test, not a product."""

    name = "example"
    description = "Example stdin reviewer"
    profile_required = False
    default_binary = "example"

    def __init__(self) -> None:
        self.seen: AgentOptions | None = None

    def runner(self, options: AgentOptions) -> Any:
        self.seen = options
        return lambda prompt: json.dumps(
            {"sections": {name: [] for name in DIMENSIONS}})

    def identity(self, options: AgentOptions) -> AgentIdentity:
        return AgentIdentity("example", source="example:test", sha256="0123456789abcdef")

    def available(self, options: AgentOptions) -> tuple[bool, str]:
        return True, "example is test-only"


def test_the_builtin_registry_lists_hermes() -> None:
    assert [adapter.name for adapter in BUILTIN] == ["hermes"]
    assert resolve("hermes").name == "hermes"


def test_an_unknown_agent_is_refused() -> None:
    with pytest.raises(ValueError, match="unknown reviewer agent"):
        resolve("not-an-agent")


def test_a_new_adapter_is_registered_and_resolved() -> None:
    registry = AgentRegistry()
    example = ExampleAdapter()
    registry.register(example)
    assert registry.get("example") is example
    with pytest.raises(ValueError, match="already registered"):
        registry.register(example)


def test_a_registered_adapter_runs_a_review_and_is_recorded(
        review_repo: Path, tmp_path: Path) -> None:
    example = ExampleAdapter()
    register(example)
    try:
        report = review(
            ReviewRequest(repo=review_repo, agent="example",
                          run_id="example-run", state_dir=tmp_path / "run"),
            example.runner(AgentOptions(binary="example")),
        )
        payload = json.loads((report.run_dir / "verdict.json").read_text(encoding="utf-8"))
        assert payload["agent"] == "example"
        assert payload["reviewer"] == "example"
        assert payload["agent_config"] == "example:test"
        assert payload["agent_config_sha256"] == "0123456789abcdef"
    finally:
        unregister("example")


def test_the_cli_lists_the_adapter_and_its_availability(
        capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["agents", "--json"]) == 0
    rows = json.loads(capsys.readouterr().out)
    assert rows[0]["name"] == "hermes"
    assert rows[0]["default_binary"] == "hermes"


def test_an_unknown_cli_agent_is_a_start_failure(
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str]) -> None:
    def no_runner(args: object, **kwargs: object) -> object:
        raise AssertionError("an unknown agent reached the reviewer runner")

    monkeypatch.setattr(cli, "_agent_runner", no_runner)
    assert cli.main(["review", "--agent", "not-an-agent"]) == 3
    assert "unknown reviewer agent" in capsys.readouterr().err


def test_the_selected_adapter_supplies_its_default_executable() -> None:
    from council.cli import _agent_options
    from council.cli_parser import build_parser

    args = build_parser().parse_args(["review", "--agent", "example"])
    options = _agent_options(args, ExampleAdapter())
    assert options.binary == "example"


def test_the_cli_passes_the_selected_agent_to_the_request() -> None:
    from council.cli import _request
    from council.cli_parser import build_parser

    args = build_parser().parse_args(
        ["review", "--agent", "example", "--reviewer", "/bin/other"])
    request = _request(args)
    assert request.agent == "example"
    assert request.reviewer == "/bin/other"
