"""Property tests for the diff parser: every hunk, every line.

`change_lines` is the one place a unified diff becomes line numbers, shared by
the `diff` proof and the context builder. The property is exact equality with
the opcodes `difflib` used to write the diff — including the multi-hunk case v1
read only where its last hunk ended.
"""

from __future__ import annotations

import difflib

from hypothesis import given
from hypothesis import strategies as st

from council.changes import change_lines, file_sections, hunk_range, hunk_sections

# Lines that cannot confuse the diff format with a newline of their own.
LINE = st.text(alphabet=st.characters(blacklist_categories=("Cc", "Cs")), max_size=20)
LINES = st.lists(LINE, max_size=30)


def _diff(old: list[str], new: list[str]) -> str:
    # unified_diff expects the lines it is given to carry their own newline.
    return "".join(
        difflib.unified_diff(
            [line + "\n" for line in old],
            [line + "\n" for line in new],
            fromfile="a/f.py",
            tofile="b/f.py",
        )
    )


def _truth(old: list[str], new: list[str]) -> tuple[set[int], set[int]]:
    """The line numbers `difflib` decided were added and removed, 1-based."""
    added: set[int] = set()
    removed: set[int] = set()
    matcher = difflib.SequenceMatcher(None, old, new)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag in ("replace", "delete"):
            removed.update(range(i1 + 1, i2 + 1))
        if tag in ("replace", "insert"):
            added.update(range(j1 + 1, j2 + 1))
    return added, removed


@given(old=LINES, new=LINES)
def test_the_parser_agrees_with_the_opcodes_that_wrote_the_diff(
    old: list[str], new: list[str]
) -> None:
    changes = change_lines(_diff(old, new))
    added, removed = _truth(old, new)
    assert changes.get("f.py", (set(), set())) == (added, removed)


@given(old=LINES, new=LINES)
def test_every_line_number_is_one_based_and_inside_its_file(
    old: list[str], new: list[str]
) -> None:
    for added, removed in change_lines(_diff(old, new)).values():
        assert all(1 <= number <= len(new) for number in added)
        assert all(1 <= number <= len(old) for number in removed)


def test_a_second_hunk_is_read_where_v1_stopped() -> None:
    """Two changes far enough apart that `difflib` writes two hunk headers."""
    old = [f"line {number}" for number in range(20)]
    new = list(old)
    new[1] = "changed near the top"
    new[18] = "changed near the bottom"
    diff = _diff(old, new)
    assert diff.count("@@ -") == 2, diff
    assert change_lines(diff)["f.py"] == ({2, 19}, {2, 19})


def test_an_empty_diff_is_empty_not_an_error() -> None:
    assert change_lines("") == {}
    assert change_lines(_diff(["same"], ["same"])) == {}


def test_a_removed_line_that_looks_like_a_file_header_is_still_a_removal() -> None:
    old = ["keep", "-- looks like a header", "keep two"]
    new = ["keep", "keep two"]
    assert change_lines(_diff(old, new))["f.py"] == (set(), {2})


def test_an_added_line_that_looks_like_a_file_header_is_still_an_addition() -> None:
    old = ["keep", "keep two"]
    new = ["keep", "++ looks like a header", "keep two"]
    assert change_lines(_diff(old, new))["f.py"] == ({2}, set())


def test_a_new_file_uses_new_side_numbers() -> None:
    diff = "".join(
        difflib.unified_diff([], ["one\n", "two\n"], fromfile="/dev/null", tofile="b/new.py")
    )
    assert change_lines(diff) == {"new.py": ({1, 2}, set())}


def test_a_diff_splits_into_one_section_per_file() -> None:
    patch = ("diff --git a/a.py b/a.py\n--- a/a.py\n+++ b/a.py\n"
             "@@ -1 +1 @@\n-x = 1\n+x = 2\n"
             "diff --git a/b.py b/b.py\n--- a/b.py\n+++ b/b.py\n"
             "@@ -1 +1 @@\n-y = 1\n+y = 2\n")
    sections = file_sections(patch)
    assert [section.path for section in sections] == ["a.py", "b.py"]
    assert "a.py" not in sections[1].text


def test_a_section_splits_into_hunks_that_keep_the_file_header() -> None:
    diff = ("diff --git a/f.py b/f.py\n--- a/f.py\n+++ b/f.py\n"
            "@@ -1,2 +1,2 @@\n a\n-b\n+B\n"
            "@@ -10,2 +10,2 @@\n j\n-k\n+K\n")
    hunks = hunk_sections(diff)
    assert len(hunks) == 2
    for hunk in hunks:
        assert hunk.startswith("diff --git a/f.py b/f.py")
        assert "+++ b/f.py" in hunk
    assert "@@ -1,2" in hunks[0]
    assert "@@ -10,2" in hunks[1]


def test_a_hunk_range_is_the_new_side() -> None:
    assert hunk_range("diff --git a/f b/f\n@@ -5,2 +7,3 @@\n") == (7, 9)
    assert hunk_range("@@ -5 +7 @@\n") == (7, 7)


def test_a_deleted_file_keeps_its_removed_lines() -> None:
    diff = "".join(
        difflib.unified_diff(["one\n", "two\n"], [], fromfile="a/gone.py", tofile="/dev/null")
    )
    assert change_lines(diff) == {"gone.py": (set(), {1, 2})}
