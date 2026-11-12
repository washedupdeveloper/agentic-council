"""SARIF 2.1.0 for findings whose proof held.

Only `PROVEN` findings become results. A claim that was refuted, or whose
evidence never settled, is not an alert: it stays in `verdict.json` with its
state, where a reader can see why the run did or did not pass.
"""

from __future__ import annotations

from .findings import Finding, State
from .schema import DIMENSIONS
from .verdict import Result

SCHEMA = "https://json.schemastore.org/sarif-2.1.0.json"
LEVEL = {"critical": "error", "high": "error", "medium": "warning", "low": "note"}
DESCRIPTION = {
    "security": "A security claim, settled by its proof.",
    "correctness": "A correctness claim, settled by its proof.",
    "performance": "A performance claim, settled by its proof.",
    "readability": "A readability claim, settled by its proof.",
    "architecture": "An architecture claim, settled by its proof.",
}
RULES = [
    {
        "id": dimension,
        "name": dimension.capitalize(),
        "shortDescription": {"text": DESCRIPTION[dimension]},
        "defaultConfiguration": {"level": "warning"},
    }
    for dimension in DIMENSIONS
]


def _location(text: str) -> tuple[str, int]:
    """`path:line` as SARIF wants it; a location without a line starts at 1."""
    path, _, raw = text.rpartition(":")
    if not path:
        return text, 1
    try:
        line = int(raw)
    except ValueError:
        return text, 1
    return path, max(1, line)


def _message(finding: Finding) -> str:
    return finding.claim + (f"\n\n{finding.detail}" if finding.detail else "")


def render(result: Result, *, tool_version: str = "0.0.0+source") -> dict[str, object]:
    """The run as a SARIF log. Proven findings only, one rule per dimension."""
    results: list[dict[str, object]] = []
    for finding in result.findings:
        if finding.state is not State.PROVEN:
            continue
        path, line = _location(finding.location)
        results.append({
            "ruleId": finding.dimension,
            "level": LEVEL.get(finding.severity, "note"),
            "message": {"text": _message(finding)},
            "locations": [{
                "physicalLocation": {
                    "artifactLocation": {"uri": path},
                    "region": {"startLine": line},
                },
            }],
            "properties": {
                "id": finding.id,
                "severity": finding.severity,
                "state": finding.state.value,
                "blocking": finding.blocks,
            },
        })
    return {
        "$schema": SCHEMA,
        "version": "2.1.0",
        "runs": [{
            "tool": {
                "driver": {
                    "name": "council",
                    "version": tool_version,
                    "rules": RULES,
                },
            },
            "results": results,
        }],
    }
