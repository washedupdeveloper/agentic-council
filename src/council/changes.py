"""Read a unified diff: which lines a change adds or removes, per file.

Pure: a string in, line numbers out. Both the `diff` proof and the context
builder read the change through this one parser, so they cannot disagree about
which lines moved.
"""

from __future__ import annotations

import re


def change_lines(diff: str) -> dict[str, tuple[set[int], set[int]]]:
    """path -> (line numbers added in the new file, line numbers removed from the old).

    Line numbers come from each hunk header, so a change with several hunks is
    read hunk by hunk rather than only where the last one ended.
    """
    changes: dict[str, tuple[set[int], set[int]]] = {}
    path: str | None = None
    old_line = new_line = 0
    for raw in diff.splitlines():
        if raw.startswith("+++ "):
            target = raw[4:].strip()
            path = None if target == "/dev/null" else (target[2:] if target.startswith("b/") else target)
            continue
        if raw.startswith("--- ") or raw.startswith("diff --git") or raw.startswith("index "):
            continue
        header = re.match(r"^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@", raw)
        if header is not None:
            old_line, new_line = int(header.group(1)), int(header.group(2))
            continue
        if path is None:
            continue
        added, removed = changes.setdefault(path, (set(), set()))
        if raw.startswith("+"):
            added.add(new_line)
            new_line += 1
        elif raw.startswith("-"):
            removed.add(old_line)
            old_line += 1
        elif raw.startswith(" "):
            old_line += 1
            new_line += 1
    return changes