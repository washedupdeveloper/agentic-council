"""The reviewer's output contract. A refusal names the exact field; an
unparsable sample is evidence that did not arrive, not "no findings"."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from .vocabulary import DIMENSIONS as DIMENSIONS  # noqa: PLC0414 - re-export for the schema contract
from .vocabulary import PROOF_KINDS as PROOF_KINDS  # noqa: PLC0414 - re-export
from .vocabulary import SEVERITIES as SEVERITIES  # noqa: PLC0414 - re-export


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
        # strict=False accepts a literal newline inside a string: the model
        # writes multi-line claims, and the bytes are unambiguous.
        value = json.loads(candidate, strict=False)
    except json.JSONDecodeError:
        # The answer may arrive inside a tool transcript; the first complete
        # object is the answer. Validation below is unchanged.
        start = candidate.find("{")
        if start == -1:
            raise SchemaError("the sample contains no JSON object") from None
        try:
            value, _ = json.JSONDecoder(strict=False).raw_decode(candidate[start:])
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
    if kind is int and isinstance(value, bool):
        raise SchemaError(f"{where}.{key}: expected int, got bool")
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
    unknown = [name for name in sections if name not in DIMENSIONS]
    if unknown:
        raise SchemaError(
            f"sections: unknown dimension(s) {', '.join(sorted(unknown))}"
        )

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
