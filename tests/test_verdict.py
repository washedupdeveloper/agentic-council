"""The verdict rule, tested exhaustively over the shape it consumes.

Every severity × state pair is exercised, not just the examples that come to
mind. The two boundary cases (`medium` proven must pass, `high` proven must
fail) are the ones a `>=`/`>` mistake breaks, so they get their own tests whose
names the claim registry cites.
"""

from __future__ import annotations

import pytest

from council.findings import SEVERITIES, Finding, State
from council.schema import DIMENSIONS
from council.verdict import Result, Verdict, exit_code, judge


def finding(severity: str = "high", state: State = State.PROVEN, ident: str = "F-1",
            dimension: str = "readability") -> Finding:
    return Finding(id=ident, dimension=dimension, severity=severity, state=state)  # type: ignore[arg-type]


def test_an_empty_run_passes() -> None:
    result = judge([])
    assert result.verdict is Verdict.PASS
    assert result.exit_code == 0


def test_every_verdict_has_one_exit_code() -> None:
    assert exit_code(Verdict.PASS) == 0
    assert exit_code(Verdict.FAIL) == 1
    assert exit_code(Verdict.INCOMPLETE) == 2
    assert judge([finding("high")]).exit_code == exit_code(Verdict.FAIL)
    assert judge([finding("high", State.UNSETTLED)]).exit_code == exit_code(Verdict.INCOMPLETE)


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


def test_a_proven_low_security_finding_blocks() -> None:
    """The tool decides: a proven security defect is not downgraded by its label."""
    assert judge([finding("low", dimension="security")]).verdict is Verdict.FAIL


def test_a_proven_low_correctness_finding_blocks() -> None:
    assert judge([finding("low", dimension="correctness")]).verdict is Verdict.FAIL


def test_a_proven_low_readability_finding_passes() -> None:
    assert judge([finding("low", dimension="readability")]).verdict is Verdict.PASS


def test_a_proven_high_readability_finding_blocks() -> None:
    assert judge([finding("high", dimension="readability")]).verdict is Verdict.FAIL


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


ALWAYS_BLOCKING = frozenset({"security", "correctness"})


@pytest.mark.parametrize("dimension", DIMENSIONS)
@pytest.mark.parametrize("severity", SEVERITIES)
@pytest.mark.parametrize("state", list(State))
def test_every_dimension_severity_and_state_has_one_outcome(
    dimension: str, severity: str, state: State,
) -> None:
    """The blocking rule has a dimension axis; a severity-only matrix misses it."""
    blocks = severity in ("high", "critical") or dimension in ALWAYS_BLOCKING
    if state is State.REFUTED or not blocks:
        expected = Verdict.PASS
    elif state is State.PROVEN:
        expected = Verdict.FAIL
    else:
        expected = Verdict.INCOMPLETE
    result: Result = judge([finding(severity, state, dimension=dimension)])
    assert result.verdict is expected


def test_a_finding_needs_an_id() -> None:
    with pytest.raises(ValueError, match="id"):
        Finding(id="", dimension="security", severity="high", state=State.PROVEN)


def test_an_unknown_severity_is_rejected() -> None:
    with pytest.raises(ValueError, match="severity"):
        finding("blocker")
