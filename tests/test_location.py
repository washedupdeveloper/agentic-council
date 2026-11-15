"""Structured finding places: a path may contain a colon."""

from __future__ import annotations

import pytest

from council.domain.location import Location
from council.findings import Finding, State


@pytest.mark.parametrize(
    ("text", "file", "line"),
    [
        ("src/a.py:12", "src/a.py", 12),
        ("src/a.py", "src/a.py", 1),
        ("docs/a:b.md", "docs/a:b.md", 1),
        ("docs/a:b.md:9", "docs/a:b.md", 9),
        ("", "", 1),
    ],
)
def test_a_location_is_split_only_at_a_trailing_line(
    text: str, file: str, line: int,
) -> None:
    parsed = Location.parse(text)
    assert (parsed.file, parsed.line) == (file, line)


def test_a_finding_exposes_the_structured_place_and_keeps_the_wire_form() -> None:
    finding = Finding(id="F-1", dimension="correctness", severity="high",
                      state=State.PROVEN, location="docs/a:b.md:9")
    assert (finding.file, finding.line) == ("docs/a:b.md", 9)
    assert finding.location == "docs/a:b.md:9"


def test_structured_fields_render_the_same_wire_form() -> None:
    finding = Finding(id="F-1", dimension="correctness", severity="high",
                      state=State.PROVEN, file="docs/a:b.md", line=9)
    assert finding.location == "docs/a:b.md:9"
