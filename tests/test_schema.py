"""The reviewer contract: every refusal names the field it refused."""

from __future__ import annotations

import json

import pytest

from council.schema import DIMENSIONS, SchemaError, parse_reviewer_output


def payload(**sections: list[dict[str, object]]) -> str:
    body = {name: [] for name in DIMENSIONS}
    body.update(sections)
    return json.dumps({"sections": body})


def finding(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "severity": "high", "file": "src/a.py", "line": 3, "claim": "The thing is wrong.",
        "proof": {"kind": "absent", "params": {"pattern": "TODO"}},
    }
    base.update(overrides)
    return base


def test_an_empty_sample_parses_to_no_findings() -> None:
    assert parse_reviewer_output(payload()).findings == ()


def test_a_fenced_sample_is_accepted() -> None:
    text = "```json\n" + payload() + "\n```"
    assert parse_reviewer_output(text).findings == ()


def test_a_finding_is_parsed_into_the_right_section() -> None:
    output = parse_reviewer_output(payload(security=[finding()]))
    assert len(output.findings) == 1
    assert output.findings[0].dimension == "security"
    assert output.in_section("correctness") == ()


def test_a_missing_section_is_named() -> None:
    body = {"sections": {name: [] for name in DIMENSIONS if name != "security"}}
    with pytest.raises(SchemaError, match="missing security"):
        parse_reviewer_output(json.dumps(body))


def test_a_finding_without_a_proof_is_refused() -> None:
    bad = {k: v for k, v in finding().items() if k != "proof"}
    with pytest.raises(SchemaError, match="proof: missing"):
        parse_reviewer_output(payload(security=[bad]))


def test_an_unknown_proof_kind_is_refused() -> None:
    bad = finding(proof={"kind": "vibes", "params": {}})
    with pytest.raises(SchemaError, match="proof.kind"):
        parse_reviewer_output(payload(security=[bad]))


def test_an_unknown_severity_is_refused() -> None:
    with pytest.raises(SchemaError, match="severity"):
        parse_reviewer_output(payload(security=[finding(severity="blocker")]))


def test_a_zero_line_is_refused() -> None:
    with pytest.raises(SchemaError, match="1-based"):
        parse_reviewer_output(payload(security=[finding(line=0)]))


def test_a_leading_dot_slash_is_refused() -> None:
    with pytest.raises(SchemaError, match="must not start"):
        parse_reviewer_output(payload(security=[finding(file="./a.py")]))


def test_a_literal_newline_inside_a_string_is_tolerated() -> None:
    """The model writes multi-line claims without escaping; the bytes are unambiguous."""
    body = payload(security=[finding(claim="first line\nsecond line")])
    literal = body.replace("\\n", "\n")
    assert parse_reviewer_output(literal).findings[0].claim == "first line\nsecond line"


def test_json_inside_a_tool_transcript_is_read() -> None:
    """The reviewer sometimes writes the file instead of answering; read the object."""
    transcript = "│ +" + payload() + "\n│ /home/user/.cache/my_review.json\n"
    assert parse_reviewer_output(transcript).findings == ()


def test_non_json_is_refused() -> None:
    with pytest.raises(SchemaError, match="no JSON object"):
        parse_reviewer_output("I reviewed the change and it looks fine.")