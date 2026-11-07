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
    read hunk by hunk rather than only where the last one ended. Inside a hunk
    every line is content, however much it looks like a file header: the hunk's
    own line counts decide when the hunk ends.
    """
    changes: dict[str, tuple[set[int], set[int]]] = {}
    path: str | None = None
    old_path: str | None = None
    old_line = new_line = 0
    old_left = new_left = 0
    for raw in diff.splitlines():
        if old_left > 0 or new_left > 0:
            prefix = raw[:1]
            if prefix == "\\":
                continue  # "\ No newline at end of file" carries no line
            added, removed = changes.setdefault(path, (set(), set())) if path else (set(), set())
            if prefix == " ":
                old_line += 1
                new_line += 1
                old_left -= 1
                new_left -= 1
            elif prefix == "-":
                if path is not None:
                    removed.add(old_line)
                old_line += 1
                old_left -= 1
            elif prefix == "+":
                if path is not None:
                    added.add(new_line)
                new_line += 1
                new_left -= 1
            continue
        if raw.startswith("--- "):
            target = raw[4:].strip()
            old_path = None if target == "/dev/null" else (target[2:] if target.startswith("a/") else target)
            continue
        if raw.startswith("+++ "):
            target = raw[4:].strip()
            if target == "/dev/null":
                path = old_path
            else:
                path = target[2:] if target.startswith("b/") else target
            continue
        header = re.match(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@", raw)
        if header is not None:
            old_line, new_line = int(header.group(1)), int(header.group(3))
            old_left = int(header.group(2)) if header.group(2) is not None else 1
            new_left = int(header.group(4)) if header.group(4) is not None else 1
            continue
    return changes