"""References are fetched by the caller, bounded, and never treated as proof."""

from __future__ import annotations

from pathlib import Path

import pytest

from council.reference import FetchError, fetch


def test_a_file_url_is_fetched(tmp_path: Path) -> None:
    path = tmp_path / "doc.txt"
    path.write_text("reference text", encoding="utf-8")
    reference = fetch(path.as_uri())
    assert reference.text == "reference text"
    assert len(reference.sha256) == 16


def test_a_reference_over_the_limit_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "big.txt"
    path.write_text("x" * 100, encoding="utf-8")
    with pytest.raises(FetchError, match="larger"):
        fetch(path.as_uri(), limit=10)


def test_a_missing_reference_is_an_error_not_an_empty_context(tmp_path: Path) -> None:
    with pytest.raises(FetchError):
        fetch((tmp_path / "missing.txt").as_uri())