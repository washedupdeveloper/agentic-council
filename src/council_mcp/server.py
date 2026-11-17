"""MCP server entry point: three tools over the public council CLI."""

from __future__ import annotations

import argparse
import sys
from typing import Any

from mcp.server.fastmcp import Context, FastMCP

from council_server.cli import (
    CouncilError,
    ReviewOptions,
    ServerConfig,
    add_server_arguments,
    config_from_args,
    run_doctor,
    run_plan,
    run_review,
)

TOOL_NAMES = ("council_plan", "council_review", "council_doctor")


def _summary(payload: dict[str, Any], result: Any) -> dict[str, Any]:
    findings = payload.get("findings")
    if not isinstance(findings, list):
        findings = []
    return {
        "verdict": payload.get("verdict"),
        "exit_code": result.returncode,
        "reason": payload.get("reason", ""),
        "findings": findings,
        "run_id": result.run_dir.name if result.run_dir else None,
        "run_dir": str(result.run_dir) if result.run_dir else None,
        "verdict_resource": (f"council://runs/{result.run_dir.name}"
                             if result.run_dir else None),
    }


def build_server(config: ServerConfig) -> FastMCP:
    """Build the server object; kept separate so tests can inspect tools."""
    mcp = FastMCP(
        "council",
        instructions=(
            "Council reviews a git change and derives a verdict from evidence. "
            "It uses the reviewer configured on the server, not the host model. "
            "A review can be PASS, FAIL, or INCOMPLETE; INCOMPLETE is not a pass."
        ),
    )

    @mcp.tool()
    async def council_plan(
        repo: str = ".",
        base: str | None = None,
        include: list[str] | None = None,
        exclude: list[str] | None = None,
        samples: int | None = None,
        context_depth: int = 3,
        ctx: Context[Any, Any, Any] | None = None,
    ) -> dict[str, Any]:
        """Show the units and prompt sizes a review would use; no model call."""
        if ctx is not None:
            await ctx.report_progress(0, 100, "preparing plan")
        options = ReviewOptions(repo=repo, base=base,
                                include=tuple(include or ()),
                                exclude=tuple(exclude or ()),
                                samples=samples, context_depth=context_depth)
        try:
            result = await run_plan(config, options)
        except CouncilError as exc:
            raise ValueError(str(exc)) from exc
        if ctx is not None:
            await ctx.report_progress(100, 100, "plan ready")
        if not isinstance(result.payload, dict):
            raise ValueError("council returned a non-object plan")
        return result.payload

    @mcp.tool()
    async def council_review(
        repo: str = ".",
        base: str | None = None,
        include: list[str] | None = None,
        exclude: list[str] | None = None,
        samples: int | None = None,
        context_depth: int = 3,
        time_budget: int = 0,
        ctx: Context[Any, Any, Any] | None = None,
    ) -> dict[str, Any]:
        """Review a change and return the verdict, findings and evidence location.

        This runs the server's configured reviewer. The host model is not the
        reviewer; the tool is a review gate, not a code-editing action.
        """
        if ctx is not None:
            await ctx.report_progress(0, 100, "starting council review")
        options = ReviewOptions(repo=repo, base=base,
                                include=tuple(include or ()),
                                exclude=tuple(exclude or ()),
                                samples=samples, context_depth=context_depth,
                                time_budget=time_budget)
        try:
            result = await run_review(config, options)
        except CouncilError as exc:
            raise ValueError(str(exc)) from exc
        if not isinstance(result.payload, dict):
            raise ValueError("council returned a non-object verdict")
        if ctx is not None:
            await ctx.report_progress(100, 100, "review finished")
        return _summary(result.payload, result)

    @mcp.tool()
    async def council_doctor(ctx: Context[Any, Any, Any] | None = None) -> list[dict[str, Any]]:
        """Check git, reviewer, profile and sandbox availability."""
        if ctx is not None:
            await ctx.report_progress(0, 100, "running council doctor")
        try:
            result = await run_doctor(config)
        except CouncilError as exc:
            raise ValueError(str(exc)) from exc
        if ctx is not None:
            await ctx.report_progress(100, 100, "doctor finished")
        if not isinstance(result.payload, list):
            raise ValueError("council returned a non-list doctor result")
        return result.payload

    @mcp.resource("council://runs/{run_id}")
    async def verdict(run_id: str) -> str:
        """The complete verdict document for a retained review."""
        path = config.state_root / run_id / "verdict.json"
        try:
            return path.read_text(encoding="utf-8")
        except OSError as exc:
            raise ValueError(f"verdict {run_id} is not retained: {exc}") from exc

    return mcp


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="council-mcp",
                                     description="MCP tools for the council review gate.")
    add_server_arguments(parser)
    args = parser.parse_args(argv)
    try:
        config = config_from_args(args)
    except SystemExit as exc:
        print(str(exc), file=sys.stderr)
        return 3
    build_server(config).run(transport="stdio")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
