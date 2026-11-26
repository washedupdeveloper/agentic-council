"""A change that is finished must be archived.

`validate --strict` checks the shape of a delta, never whether the work is recorded as
done: a change with every task ticked validates perfectly and stays in `changes/` until
someone archives it. Three such changes sat in this tree -- 41/41, 11/11 and 16/16 -- long
after their work merged, which is the record drifting from the tree it describes.

So: every task ticked means the change is finished, and a finished change lives in
`archive/`. The check is vacuous when there are no open changes, which is the normal state.
"""

from __future__ import annotations

import re
from pathlib import Path

CHANGES = Path(__file__).resolve().parent.parent / "openspec" / "changes"
BOX = re.compile(r"^\s*- \[([ xX])\]", re.MULTILINE)


def _open_changes() -> list[Path]:
    return sorted(p for p in CHANGES.iterdir() if p.is_dir() and p.name != "archive")


def _boxes(tasks: Path) -> list[str]:
    return BOX.findall(tasks.read_text(encoding="utf-8"))


def test_a_finished_change_is_not_left_open() -> None:
    finished = []
    for change in _open_changes():
        tasks = change / "tasks.md"
        if not tasks.is_file():
            continue
        ticks = _boxes(tasks)
        if ticks and all(tick.lower() == "x" for tick in ticks):
            finished.append(f"{change.name} ({len(ticks)}/{len(ticks)} tasks)")

    assert not finished, (
        "these changes have every task ticked and are still open:\n  "
        + "\n  ".join(finished)
        + "\n\nA finished change is archived in the same commit as its last task:\n"
        "  nix run .#openspec -- archive <name> --yes\n"
        "If the work is not actually finished, untick the task that is still open."
    )


def test_the_change_directories_are_readable() -> None:
    """Guard the guard: an empty or missing tree must not look like a pass."""
    assert CHANGES.is_dir(), f"{CHANGES} does not exist"
    for change in _open_changes():
        assert (change / "proposal.md").is_file(), f"{change.name} has no proposal.md"

def test_an_open_change_records_its_evidence() -> None:
    """A change in flight carries the commands that settle its claims.

    `tasks.md` says what is done; evidence says how anyone can tell. A ticked task with
    no command behind it is unproven, and the difference between "finished" and "I think
    it is finished" is exactly the row the reader needs. Archived changes are the record
    of work already gated; this applies to the ones still open.
    """
    missing = []
    for change in _open_changes():
        tasks = change / "tasks.md"
        if not tasks.is_file():
            continue
        if "## Evidence" not in tasks.read_text(encoding="utf-8"):
            missing.append(change.name)
    assert not missing, (
        "these open changes have no `## Evidence` section in tasks.md:\n  "
        + "\n  ".join(missing)
        + "\n\nOne row per ticked task: | claim | command | result |. "
        "See docs/sdd.md."
    )
