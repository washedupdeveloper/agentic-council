"""ACP external-agent adapter for the council review gate."""

from __future__ import annotations

import argparse
import asyncio
import shlex
import sys
from dataclasses import dataclass, field, replace
from typing import Any
from uuid import uuid4

from acp import (
    Agent,
    InitializeResponse,
    NewSessionResponse,
    PromptResponse,
    run_agent,
)
from acp.interfaces import Client
from acp.schema import (
    AgentCapabilities,
    AgentMessageChunk,
    AudioContentBlock,
    AuthenticateResponse,
    AvailableCommand,
    AvailableCommandsUpdate,
    ClientCapabilities,
    CloseSessionResponse,
    EmbeddedResourceContentBlock,
    ForkSessionResponse,
    ImageContentBlock,
    Implementation,
    ListSessionsResponse,
    LoadSessionResponse,
    ResourceContentBlock,
    ResumeSessionResponse,
    SetSessionConfigOptionResponse,
    SetSessionModeResponse,
    TextContentBlock,
)
from council import __version__

from council_server.cli import (
    CouncilError,
    ReviewOptions,
    ServerConfig,
    add_server_arguments,
    config_from_args,
    local_path,
    run_plan,
    run_review,
)


@dataclass
class Session:
    cwd: str
    config: ServerConfig
    task: asyncio.Task[Any] | None = None
    last: dict[str, Any] | None = None


_COMMANDS = [
    AvailableCommand(name="plan", description="Show review units, prompt sizes and sample cost"),
    AvailableCommand(name="review", description="Review the workspace and report a verdict"),
    AvailableCommand(name="verdict", description="Show the last verdict"),
    AvailableCommand(name="help", description="Show council commands"),
]


@dataclass
class CouncilAgent(Agent):
    config: ServerConfig
    sessions: dict[str, Session] = field(default_factory=dict)
    conn: Client | None = None

    def on_connect(self, conn: Client) -> None:
        self.conn = conn

    async def initialize(
        self,
        protocol_version: int,
        client_capabilities: ClientCapabilities | None = None,
        client_info: Implementation | None = None,
        **kwargs: Any,
    ) -> InitializeResponse:
        return InitializeResponse(
            protocol_version=protocol_version,
            agent_info=Implementation(name="council", title="Council review gate",
                                      version=__version__),
            agent_capabilities=AgentCapabilities(load_session=True),
        )

    async def new_session(
        self,
        cwd: str,
        additional_directories: list[str] | None = None,
        mcp_servers: list[Any] | None = None,
        **kwargs: Any,
    ) -> NewSessionResponse:
        path = local_path(cwd).expanduser()
        if not path.is_dir():
            raise ValueError(f"workspace is not a directory: {cwd}")
        session_id = uuid4().hex
        workspace = path.resolve()
        self.sessions[session_id] = Session(
            str(workspace), replace(self.config, root=workspace))
        # A session update sent while session/new is still in flight makes the
        # Zed ACP client close the transport. Let the response leave first.
        asyncio.create_task(self._announce_commands(session_id))
        return NewSessionResponse(session_id=session_id)

    async def load_session(
        self,
        cwd: str,
        session_id: str,
        mcp_servers: list[Any] | None = None,
        additional_directories: list[str] | None = None,
        **kwargs: Any,
    ) -> LoadSessionResponse | None:
        path = local_path(cwd).expanduser()
        if not path.is_dir():
            raise ValueError(f"workspace is not a directory: {cwd}")
        workspace = path.resolve()
        self.sessions[session_id] = Session(
            str(workspace), replace(self.config, root=workspace))
        asyncio.create_task(self._announce_commands(session_id))
        return LoadSessionResponse()

    async def list_sessions(self, cwd: str | None = None,
                            cursor: str | None = None,
                            **kwargs: Any) -> ListSessionsResponse:
        return ListSessionsResponse(sessions=[])

    async def set_session_mode(self, session_id: str, mode_id: str,
                               **kwargs: Any) -> SetSessionModeResponse | None:
        return None

    async def set_config_option(self, config_id: str, session_id: str,
                                value: str | bool,
                                **kwargs: Any) -> SetSessionConfigOptionResponse | None:
        return None

    async def authenticate(self, method_id: str,
                           **kwargs: Any) -> AuthenticateResponse | None:
        return None

    async def fork_session(self, session_id: str, cwd: str,
                           additional_directories: list[str] | None = None,
                           mcp_servers: list[Any] | None = None,
                           **kwargs: Any) -> ForkSessionResponse:
        raise NotImplementedError("forking a council session is not supported")

    async def resume_session(self, session_id: str, cwd: str,
                             additional_directories: list[str] | None = None,
                             mcp_servers: list[Any] | None = None,
                             **kwargs: Any) -> ResumeSessionResponse:
        return ResumeSessionResponse()

    async def close_session(self, session_id: str,
                            **kwargs: Any) -> CloseSessionResponse | None:
        self.sessions.pop(session_id, None)
        return CloseSessionResponse()

    async def ext_method(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        return {}

    async def ext_notification(self, method: str, params: dict[str, Any]) -> None:
        return None

    async def prompt(
        self,
        session_id: str,
        prompt: list[TextContentBlock | ImageContentBlock | AudioContentBlock
                    | ResourceContentBlock | EmbeddedResourceContentBlock],
        **kwargs: Any,
    ) -> PromptResponse:
        session = self.sessions.get(session_id)
        if session is None:
            raise ValueError(f"unknown session: {session_id}")
        text = "\n".join(block.text for block in prompt
                         if isinstance(block, TextContentBlock)).strip()
        task = asyncio.current_task()
        session.task = task
        try:
            if text.startswith("/help") or text == "":
                await self._send(session_id, _HELP)
                return PromptResponse(stop_reason="end_turn")
            if text.startswith("/verdict"):
                await self._send(session_id, _verdict_text(session.last))
                return PromptResponse(stop_reason="end_turn")
            options = _parse_command(text)
            if options is None:
                await self._send(session_id, _HELP)
                return PromptResponse(stop_reason="end_turn")
            options = replace(options, repo=session.cwd)
            await self._send(session_id, "council: working…")
            if text.startswith("/plan"):
                result = await run_plan(session.config, options)
                await self._send(session_id, _plan_text(result.payload))
            else:
                result = await run_review(session.config, options)
                if isinstance(result.payload, dict):
                    session.last = result.payload
                await self._send(session_id, _review_text(result.payload, result.stderr))
            return PromptResponse(stop_reason="end_turn")
        except asyncio.CancelledError:
            await self._send(session_id, "council: cancelled")
            return PromptResponse(stop_reason="cancelled")
        except (CouncilError, ValueError) as exc:
            await self._send(session_id, f"council: {exc}")
            return PromptResponse(stop_reason="end_turn")
        finally:
            session.task = None

    async def cancel(self, session_id: str, **kwargs: Any) -> None:
        session = self.sessions.get(session_id)
        if session is not None and session.task is not None:
            session.task.cancel()

    async def _announce_commands(self, session_id: str) -> None:
        await asyncio.sleep(1.0)
        if session_id in self.sessions:
            await self._publish_commands(session_id)

    async def _publish_commands(self, session_id: str) -> None:
        if self.conn is None:
            return
        await self.conn.session_update(
            session_id,
            AvailableCommandsUpdate(session_update="available_commands_update",
                                    available_commands=_COMMANDS),
        )

    async def _send(self, session_id: str, text: str) -> None:
        if self.conn is None:
            return
        await self.conn.session_update(
            session_id,
            AgentMessageChunk(session_update="agent_message_chunk",
                              content=TextContentBlock(type="text", text=text)),
        )


_HELP = """\
council is a review gate.

/plan    show units, prompt sizes and sample cost; no model call
/review  review the current workspace and return a verdict
/verdict show the last verdict
/help    this message

The reviewer is configured on the council-acp server, not by this chat.
"""


def _parse_command(text: str) -> ReviewOptions | None:
    """Recognise /plan and /review with a deliberately small option surface."""
    words = shlex.split(text)
    if not words or words[0] not in ("/plan", "/review"):
        return None
    index = 1
    base: str | None = None
    include: list[str] = []
    exclude: list[str] = []
    samples: int | None = None
    depth = 3
    budget = 0
    while index < len(words):
        word = words[index]
        if word in ("--base", "--include", "--exclude", "--samples",
                    "--context-depth", "--time-budget"):
            if index + 1 >= len(words):
                return None
            value = words[index + 1]
            if word == "--base":
                base = value
            elif word == "--include":
                include.append(value)
            elif word == "--exclude":
                exclude.append(value)
            elif word == "--samples":
                try:
                    samples = int(value)
                except ValueError:
                    return None
            elif word == "--context-depth":
                try:
                    depth = int(value)
                except ValueError:
                    return None
            else:
                try:
                    budget = int(value)
                except ValueError:
                    return None
            index += 2
            continue
        return None
    return ReviewOptions(repo=".", base=base, include=tuple(include),
                         exclude=tuple(exclude), samples=samples,
                         context_depth=depth, time_budget=budget)


def _plan_text(payload: Any) -> str:
    if not isinstance(payload, dict):
        return "council: plan returned an unexpected result"
    units = payload.get("units", [])
    return (
        f"PLAN  {payload.get('prompt_bytes', '?')} bytes; "
        f"limit {payload.get('prompt_limit', '?')}\n"
        f"units: {len(units) if isinstance(units, list) else '?'}; "
        f"windows: {payload.get('windows', 0)}\n"
        f"estimated samples: {payload.get('estimated_samples')}"
    )


def _review_text(payload: Any, stderr: str) -> str:
    if not isinstance(payload, dict):
        return "council: review returned an unexpected result"
    findings = payload.get("findings", [])
    if not isinstance(findings, list):
        findings = []
    lines = [f"{str(payload.get('verdict', 'UNKNOWN')).upper()}  "
             f"exit {payload.get('exit_code', '?')}",
             f"reason: {payload.get('reason', '')}"]
    for finding in findings:
        if isinstance(finding, dict):
            lines.append(f"- {finding.get('state', '')} "
                         f"{finding.get('severity', '')} "
                         f"{finding.get('location', '')}: "
                         f"{finding.get('claim', '')}")
    if stderr.strip():
        lines.append(f"notes: {stderr.strip().splitlines()[-1]}")
    return "\n".join(lines)


def _verdict_text(payload: dict[str, Any] | None) -> str:
    if payload is None:
        return "council: no review has run in this session"
    return _review_text(payload, "")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="council-acp",
                                     description="ACP external agent for council.")
    add_server_arguments(parser)
    args = parser.parse_args(argv)
    try:
        config = config_from_args(args)
    except SystemExit as exc:
        print(str(exc), file=sys.stderr)
        return 3
    asyncio.run(run_agent(CouncilAgent(config)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
