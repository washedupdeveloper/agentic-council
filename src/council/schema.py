"""The reviewer's output contract, enforced before anything is believed.

The model returns one JSON object with five sections. This module turns that
text into typed findings or refuses it with a path to the exact field that is
wrong — a sample that cannot be parsed is evidence that did not arrive, not a
sample with no findings.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

DIMENSIONS: tuple[str, ...] = (
    "security",
    "correctness",
    "readability",
    "architecture",
    "performance",
)
SEVERITIES: tuple[str, ...] = ("low", "medium", "high", "critical")
PROOF_KINDS: tuple[str, ...] = ("absent", "present", "command", "json", "http", "dom", "diff")


class SchemaError(ValueError):
    """The sample is not the shape the contract declares."""


@dataclass(frozen=True, slots=True)
class RawFinding:
    """One finding as the reviewer wrote it, before any merge or adjudication."""

    dimension: str
    severity: str
    file: str
    line: int
    claim: str
    proof_kind: str
    proof_params: dict[str, Any]


@dataclass(frozen=True, slots=True)
class ReviewerOutput:
    findings: tuple[RawFinding, ...]

    def in_section(self, dimension: str) -> tuple[RawFinding, ...]:
        return tuple(f for f in self.findings if f.dimension == dimension)


def _strip_fence(text: str) -> str:
    """Remove a markdown fence if the model wrapped its JSON in one."""
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    lines = stripped.splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()


def _payload(text: str) -> dict[str, Any]:
    candidate = _strip_fence(text)
    try:
        value = json.loads(candidate)
    except json.JSONDecodeError:
        start, end = candidate.find("{"), candidate.rfind("}")
        if start == -1 or end <= start:
            raise SchemaError("the sample contains no JSON object") from None
        try:
            value = json.loads(candidate[start:end + 1])
        except json.JSONDecodeError as exc:
            raise SchemaError(f"the sample is not valid JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise SchemaError("the sample's JSON is not an object")
    return value


def _field(entry: dict[str, Any], key: str, where: str, *, kind: type) -> Any:
    if key not in entry:
        raise SchemaError(f"{where}.{key}: missing")
    value = entry[key]
    if not isinstance(value, kind):
        raise SchemaError(f"{where}.{key}: expected {kind.__name__}, got {type(value).__name__}")
    if isinstance(value, str) and not value.strip():
        raise SchemaError(f"{where}.{key}: empty")
    return value


def parse_reviewer_output(text: str) -> ReviewerOutput:
    """Parse one sample. Anything malformed raises `SchemaError` naming the field."""
    payload = _payload(text)
    sections = payload.get("sections")
    if not isinstance(sections, dict):
        raise SchemaError("sections: missing or not an object")

    missing = [name for name in DIMENSIONS if name not in sections]
    if missing:
        raise SchemaError(f"sections: missing {', '.join(missing)}")

    findings: list[RawFinding] = []
    for dimension in DIMENSIONS:
        entries = sections[dimension]
        if not isinstance(entries, list):
            raise SchemaError(f"sections.{dimension}: expected a list")
        for index, entry in enumerate(entries):
            where = f"sections.{dimension}[{index}]"
            if not isinstance(entry, dict):
                raise SchemaError(f"{where}: expected an object")
            severity = _field(entry, "severity", where, kind=str)
            if severity not in SEVERITIES:
                raise SchemaError(f"{where}.severity: {severity!r} is not one of {SEVERITIES}")
            path = _field(entry, "file", where, kind=str)
            if path.startswith("./"):
                raise SchemaError(f"{where}.file: {path!r} must not start with './'")
            line = _field(entry, "line", where, kind=int)
            if line < 1:
                raise SchemaError(f"{where}.line: {line} is not a 1-based line")
            claim = _field(entry, "claim", where, kind=str)
            proof = _field(entry, "proof", where, kind=dict)
            kind = _field(proof, "kind", f"{where}.proof", kind=str)
            if kind not in PROOF_KINDS:
                raise SchemaError(
                    f"{where}.proof.kind: {kind!r} is not one of {PROOF_KINDS}")
            params = _field(proof, "params", f"{where}.proof", kind=dict)
            findings.append(RawFinding(
                dimension=dimension, severity=severity, file=path, line=line,
                claim=claim, proof_kind=kind, proof_params=dict(params),
            ))
    return ReviewerOutput(tuple(findings))