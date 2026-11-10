"""SARIF: proven findings become alerts; nothing unsettled is reported as one."""

from __future__ import annotations

from council.findings import Finding, State
from council.sarif import render
from council.schema import DIMENSIONS
from council.verdict import Result, Verdict


def finding(state: State, *, severity: str = "critical", location: str = "a.py:2",
            identifier: str = "F-01", dimension: str = "security") -> Finding:
    return Finding(identifier, dimension, severity, state, location,
                   "A claim.", "The detail.")


def test_proven_findings_become_sarif_results() -> None:
    payload = render(Result(Verdict.FAIL, "a finding", (finding(State.PROVEN),)))
    assert payload["$schema"].endswith("sarif-2.1.0.json")
    assert payload["version"] == "2.1.0"
    run = payload["runs"][0]
    assert [rule["id"] for rule in run["tool"]["driver"]["rules"]] == list(DIMENSIONS)
    result = run["results"][0]
    assert result["ruleId"] == "security"
    assert result["level"] == "error"
    location = result["locations"][0]["physicalLocation"]
    assert location["artifactLocation"]["uri"] == "a.py"
    assert location["region"]["startLine"] == 2
    assert result["properties"] == {"id": "F-01", "severity": "critical",
                                    "state": "proven", "blocking": True}


def test_unproven_findings_are_not_alerts() -> None:
    findings = (finding(State.REFUTED, identifier="F-01"),
                finding(State.UNSETTLED, identifier="F-02"),
                finding(State.UNRUNNABLE, identifier="F-03"))
    run = render(Result(Verdict.INCOMPLETE, "missing", findings))["runs"][0]
    assert run["results"] == []


def test_severity_maps_to_sarif_level() -> None:
    levels = {severity: render(Result(Verdict.FAIL, "", (finding(
        State.PROVEN, severity=severity),)))["runs"][0]["results"][0]["level"]
        for severity in ("critical", "high", "medium", "low")}
    assert levels == {"critical": "error", "high": "error",
                      "medium": "warning", "low": "note"}


def test_a_location_without_a_line_starts_at_one() -> None:
    result = render(Result(Verdict.FAIL, "", (finding(
        State.PROVEN, location="README.md"),)))["runs"][0]["results"][0]
    assert result["locations"][0]["physicalLocation"]["region"]["startLine"] == 1
