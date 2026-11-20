"""End-to-end MCP: a real MCP client, a real council CLI, a fake reviewer."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from conftest import SOURCE


def server_args(repo: Path, tmp_path: Path, reviewer: Path) -> list[str]:
    return [
        "-m", "council_mcp",
        "--repo-root", str(repo),
        "--state-root", str(tmp_path / "state"),
        "--reviewer", str(reviewer),
        "--profile", "test",
        "--no-sandbox",
    ]


def structured(result: Any) -> Any:
    value = getattr(result, "structured_content", None)
    if value is None:
        value = getattr(result, "structuredContent", None)
    if value is not None:
        return value
    for content in result.content:
        if getattr(content, "type", None) == "text":
            return json.loads(content.text)
    raise AssertionError("tool returned no structured content")


async def call(
    repo: Path, tmp_path: Path, reviewer: Path, tool: str,
    arguments: dict[str, Any],
) -> tuple[Any, Any]:
    params = StdioServerParameters(
        command=sys.executable,
        args=server_args(repo, tmp_path, reviewer),
        cwd=str(tmp_path),
        env=_env(),
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            listed = await session.list_tools()
            result = await session.call_tool(tool, arguments=arguments)
            return listed, result


def _env() -> dict[str, str]:
    import os

    env = os.environ.copy()
    env["PYTHONPATH"] = str(SOURCE) + (
        os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else ""
    )
    return env


def test_mcp_lists_the_three_tools(review_repo: Path, tmp_path: Path,
                                   fake_reviewer: Path) -> None:
    async def run() -> None:
        listed, _ = await call(review_repo, tmp_path, fake_reviewer,
                               "council_plan", {"repo": ".", "base": "HEAD~1"})
        assert {tool.name for tool in listed.tools} == {
            "council_plan", "council_review", "council_doctor"}

    asyncio.run(run())


def test_mcp_plan_is_the_cli_plan(review_repo: Path, tmp_path: Path,
                                  fake_reviewer: Path) -> None:
    async def run() -> None:
        _, result = await call(review_repo, tmp_path, fake_reviewer,
                               "council_plan", {"repo": ".", "base": "HEAD~1"})
        payload = structured(result)
        assert payload["base"]
        assert payload["head"]
        assert isinstance(payload["units"], list)

    asyncio.run(run())


def test_mcp_review_runs_the_gate_and_exposes_evidence(
        review_repo: Path, tmp_path: Path, fake_reviewer: Path) -> None:
    async def run() -> None:
        _, result = await call(review_repo, tmp_path, fake_reviewer,
                               "council_review", {"repo": ".", "base": "HEAD~1"})
        payload = structured(result)
        assert payload["verdict"] == "fail"
        assert payload["exit_code"] == 1
        assert payload["findings"][0]["state"] == "proven"
        assert payload["findings"][0]["dimension"] == "security"
        assert payload["run_dir"]
        assert Path(payload["run_dir"], "verdict.json").is_file()
        assert payload["verdict_resource"].startswith("council://runs/")

    asyncio.run(run())


def test_mcp_doctor_reports_the_fake_reviewer(
        review_repo: Path, tmp_path: Path, fake_reviewer: Path) -> None:
    async def run() -> None:
        _, result = await call(review_repo, tmp_path, fake_reviewer,
                               "council_doctor", {})
        checks = structured(result)
        if isinstance(checks, dict) and isinstance(checks.get("result"), list):
            checks = checks["result"]
        assert isinstance(checks, list)
        assert {check["name"] for check in checks} >= {"git", "reviewer", "agent"}

    asyncio.run(run())


def test_mcp_verdict_is_retained_as_a_resource(
        review_repo: Path, tmp_path: Path, fake_reviewer: Path) -> None:
    async def run() -> None:
        params = StdioServerParameters(
            command=sys.executable,
            args=server_args(review_repo, tmp_path, fake_reviewer),
            cwd=str(tmp_path),
            env=_env(),
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(
                    "council_review", {"repo": ".", "base": "HEAD~1"})
                payload = structured(result)
                resource = await session.read_resource(payload["verdict_resource"])
                body = resource.contents[0]
                text = getattr(body, "text", "")
                assert json.loads(text)["verdict"] == "fail"

    asyncio.run(run())


def test_mcp_refuses_a_repository_outside_its_root(
        review_repo: Path, tmp_path: Path, fake_reviewer: Path) -> None:
    async def run() -> None:
        _, result = await call(review_repo, tmp_path, fake_reviewer,
                               "council_plan", {"repo": "../outside"})
        if not result.isError:
            raise AssertionError("an outside repository must be refused")

    asyncio.run(run())
