"""The instrument's identity: what the digest covers, and what it must not."""

from __future__ import annotations

import pytest

from council.domain.prompt import CONTRACT, PromptError, instrument_digest, render
from council.domain.schema import PROOF_KINDS, SEVERITIES

TEMPLATE = "Base {{base}}\n\n{{diff}}"


def test_render_fills_both_placeholders() -> None:
    text = render(TEMPLATE, base="abc123", diff="+x = 1")
    assert "Base abc123" in text
    assert "+x = 1" in text
    assert "{{" not in text


def test_a_template_without_placeholders_is_refused() -> None:
    with pytest.raises(PromptError, match="missing"):
        render("nothing to fill", base="a", diff="b")


def test_the_digest_is_stable_for_the_same_instrument() -> None:
    first = instrument_digest(TEMPLATE, profile="council-generalist")
    second = instrument_digest(TEMPLATE, profile="council-generalist")
    assert first == second
    assert len(first) == 16


def test_the_digest_changes_with_the_prompt() -> None:
    assert instrument_digest(TEMPLATE, profile="p") != instrument_digest(TEMPLATE + " ", profile="p")


def test_the_digest_changes_with_the_profile() -> None:
    assert instrument_digest(TEMPLATE, profile="a") != instrument_digest(TEMPLATE, profile="b")


def test_the_digest_changes_with_the_contract() -> None:
    assert instrument_digest(TEMPLATE, profile="p", contract="a") != \
        instrument_digest(TEMPLATE, profile="p", contract="b")


def test_the_contract_names_every_kind_and_severity() -> None:
    assert all(kind in CONTRACT for kind in PROOF_KINDS)
    assert all(severity in CONTRACT for severity in SEVERITIES)


def test_the_digest_changes_with_the_dimensions() -> None:
    assert instrument_digest(TEMPLATE, profile="p", dimensions=("security",)) != \
        instrument_digest(TEMPLATE, profile="p", dimensions=("security", "correctness"))


def test_the_digest_covers_the_profile_configuration() -> None:
    """Two profiles with the same name and different models are instruments apart."""
    assert instrument_digest(TEMPLATE, profile="p") != \
        instrument_digest(TEMPLATE, profile="p", profile_fingerprint="deadbeef")


def test_an_unread_profile_configuration_is_recorded_as_unknown() -> None:
    """An empty fingerprint and no fingerprint are the same statement: not known."""
    assert instrument_digest(TEMPLATE, profile="p") == \
        instrument_digest(TEMPLATE, profile="p", profile_fingerprint="")
