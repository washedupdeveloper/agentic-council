"""The verdict rule, tested exhaustively over the shape it consumes.

Every severity × state pair is exercised, not just the examples that come to
mind. The two boundary cases (`medium` proven must pass, `high` proven must
fail) are the ones a `>=`/`>` mistake breaks, so they get their own tests whose
names the claim registry cites.
"""

from __future__ import annotations

import pytest

from reviewc.findings import SEVERITIES, Finding, State
from reviewc.verdict import Result, Verdict, judge


def finding(severity: str = "high", state: State = State.PROVEN, ident: str = "F-1") -> Finding:
    return Finding(id=ident, dimension="security", severity=severity, state=state)  # type: ignore[arg-type]


def test_an_empty_run_passes() -> None:
    result = judge([])
    assert result.verdict is Verdict.PASS
    assert result.exit_code == 0


def test_a_proven_high_fails() -> None:
    result = judge([finding("high")])
    assert result.verdict is Verdict.FAIL
    assert result.exit_code == 1
    assert "F-1" in result.reason


def test_a_proven_critical_fails() -> None:
    assert judge([finding("critical")]).verdict is Verdict.FAIL


def test_a_proven_medium_passes() -> None:
    """The boundary: medium is not blocking, and a rule written `>= medium` fails here."""
    result = judge([finding("medium")])
    assert result.verdict is Verdict.PASS
    assert "non-blocking" in result.reason


def test_a_proven_low_passes() -> None:
    assert judge([finding("low")]).verdict is Verdict.PASS


def test_a_refuted_high_passes() -> None:
    assert judge([finding("high", State.REFUTED)]).verdict is Verdict.PASS


def test_an_unsettled_high_is_incomplete() -> None:
    result = judge([finding("high", State.UNSETTLED)])
    assert result.verdict is Verdict.INCOMPLETE
    assert result.exit_code == 2
    assert "could not be settled" in result.reason


def test_an_unrunnable_high_is_incomplete() -> None:
    assert judge([finding("high", State.UNRUNNABLE)]).verdict is Verdict.INCOMPLETE


def test_fail_outranks_incomplete() -> None:
    result = judge([finding("high", State.UNSETTLED, "OPEN-1"),
                    finding("critical", State.PROVEN, "REAL-1")])
    assert result.verdict is Verdict.FAIL
    assert "REAL-1" in result.reason


def test_the_reason_cites_at_most_three_ids() -> None:
    many = [finding("high", ident=f"F-{n}") for n in range(5)]
    reason = judge(many).reason
    assert "+2 more" in reason
    assert reason.count("F-") == 3


@pytest.mark.parametrize("severity", SEVERITIES)
@pytest.mark.parametrize("state", list(State))
def test_every_pair_has_one_outcome(severity: str, state: State) -> None:
    """Exhaustive over 4 severities × 4 states: the rule is total."""
    result: Result = judge([finding(severity, state)])
    expected = {
        (State.PROVEN, True): Verdict.FAIL,
        (State.PROVEN, False): Verdict.PASS,
        (State.REFUTED, True): Verdict.PASS,
        (State.REFUTED, False): Verdict.PASS,
        (State.UNSETTLED, True): Verdict.INCOMPLETE,
        (State.UNSETTLED, False): Verdict.PASS,
        (State.UNRUNNABLE, True): Verdict.INCOMPLETE,
        (State.UNRUNNABLE, False): Verdict.PASS,
    }[(state, severity in ("high", "critical"))]
    assert result.verdict is expected


def test_a_finding_needs_an_id() -> None:
    with pytest.raises(ValueError, match="id"):
        Finding(id="", dimension="security", severity="high", state=State.PROVEN)


def test_an_unknown_severity_is_rejected() -> None:
    with pytest.raises(ValueError, match="severity"):
        finding("blocker")