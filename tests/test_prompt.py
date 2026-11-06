"""The instrument's identity: what the digest covers, and what it must not."""

from __future__ import annotations

import pytest

from council.prompt import PromptError, instrument_digest, render

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


def test_the_digest_changes_with_the_dimensions() -> None:
    assert instrument_digest(TEMPLATE, profile="p", dimensions=("security",)) != \
        instrument_digest(TEMPLATE, profile="p", dimensions=("security", "correctness"))