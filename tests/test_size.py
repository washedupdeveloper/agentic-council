"""A ratchet on the tree's size, because a stated budget was not a gate.

M11 argued the 4,000-line cap was the constraint that prevented multi-reason
modules, and then the tree passed it: 5,515 source lines at `dda59bc`, with no
test to notice. A budget that lives only in a milestone page is a wish. These two
numbers are ratchets: crossing one is a decision taken in a diff, with a commit
message that says why, not a drift nobody sees.
"""

from __future__ import annotations

from pathlib import Path

SOURCE = Path(__file__).resolve().parent.parent / "src" / "council"

#: Raise a ratchet deliberately, in the diff that needs the room.
#: The adapter seam adds an explicit package boundary; the evidence sidecar
#: adds one local-only module without touching the review loop. The direct
#: reviewer adapter adds one effect module at the same seam. The doctor source
#: check and the single-sample opt-in add one guard each.
SOURCE_LIMIT = 6740
MODULE_LIMIT = 50


def modules() -> list[Path]:
    return sorted(SOURCE.rglob("*.py"))


def test_the_source_stays_under_the_line_ratchet() -> None:
    lines = sum(len(path.read_text(encoding="utf-8").splitlines()) for path in modules())
    assert lines <= SOURCE_LIMIT, f"{lines} source lines; the ratchet is {SOURCE_LIMIT}"


def test_the_module_count_stays_under_the_ratchet() -> None:
    count = len(modules())
    assert count <= MODULE_LIMIT, f"{count} modules; the ratchet is {MODULE_LIMIT}"
