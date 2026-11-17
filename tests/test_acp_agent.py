"""End-to-end ACP: the official SDK client drives the real CLI adapter."""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

from acp import PROTOCOL_VERSION
from acp.schema import AgentMessageChunk, ClientCapabilities, TextContentBlock
from acp.stdio import spawn_agent_process

from conftest import SOURCE


class RecordingClient:
    def __init__(self) -> None:
        self.updates: list[AgentMessageChunk] = []

    async def session_update(self, session_id: str, update: AgentMessageChunk,
                             **kwargs: object) -> None:
        self.updates.append(update)


def env() -> dict[str, str]:
    value = os.environ.copy()
    value["PYTHONPATH"] = str(SOURCE) + (
        os.pathsep + value["PYTHONPATH"] if value.get("PYTHONPATH") else ""
    )
    return value


def args(repo: Path, tmp_path: Path, reviewer: Path) -> list[str]:
    return [
        "-m", "council_acp",
        "--repo-root", str(repo),
        "--state-root", str(tmp_path / "state"),
        "--reviewer", str(reviewer),
        "--profile", "test",
        "--no-sandbox",
    ]


def text_of(update: AgentMessageChunk) -> str:
    content = update.content
    return getattr(content, "text", "")


async def run_prompt(repo: Path, tmp_path: Path, reviewer: Path,
                     command: str) -> tuple[list[str], str]:
    client = RecordingClient()
    async with spawn_agent_process(
        lambda conn: client,
        sys.executable, *args(repo, tmp_path, reviewer),
        cwd=str(tmp_path), env=env(),
    ) as (connection, process):
        initialized = await connection.initialize(
            protocol_version=PROTOCOL_VERSION,
            client_capabilities=ClientCapabilities(),
        )
        assert initialized.protocol_version
        session = await connection.new_session(cwd=str(repo))
        response = await connection.prompt(
            session.session_id,
            [TextContentBlock(type="text", text=command)],
        )
        updates = [text_of(update) for update in client.updates]
        return updates, response.stop_reason


def test_acp_plan_runs_without_a_model(review_repo: Path, tmp_path: Path,
                                       fake_reviewer: Path) -> None:
    updates, stop = asyncio.run(run_prompt(review_repo, tmp_path, fake_reviewer,
                                           "/plan"))
    assert stop == "end_turn"
    assert any("PLAN" in update for update in updates)
    assert any("units:" in update for update in updates)


def test_acp_review_returns_the_gate_verdict(review_repo: Path, tmp_path: Path,
                                             fake_reviewer: Path) -> None:
    updates, stop = asyncio.run(run_prompt(review_repo, tmp_path, fake_reviewer,
                                           "/review"))
    assert stop == "end_turn"
    joined = "\n".join(updates)
    assert "FAIL" in joined
    assert "A password is committed." in joined
    assert "reason:" in joined


def test_acp_help_is_deterministic(review_repo: Path, tmp_path: Path,
                                   fake_reviewer: Path) -> None:
    updates, stop = asyncio.run(run_prompt(review_repo, tmp_path, fake_reviewer,
                                           "/help"))
    assert stop == "end_turn"
    assert any("/review" in update for update in updates)
