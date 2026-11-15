"""Read a unified diff: which lines a change adds or removes, per file.

Pure: a string in, line numbers out. Both the `diff` proof and the context
builder read the change through this one parser, so they cannot disagree about
which lines moved.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class FileSection:
    """One file's part of a unified diff, header included."""

    path: str
    text: str


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


def _section_path(text: str) -> str | None:
    """The path a file section is about, from the header rather than a hunk."""
    for line in text.splitlines():
        if line.startswith("+++ "):
            target = line[4:].strip()
            if target != "/dev/null":
                return target[2:] if target.startswith("b/") else target
        if line.startswith("--- "):
            target = line[4:].strip()
            if target != "/dev/null":
                return target[2:] if target.startswith("a/") else target
    for line in text.splitlines():
        if line.startswith("diff --git "):
            parts = line.split()
            if len(parts) >= 4:
                return parts[2][2:] if parts[2].startswith("a/") else parts[2]
    return None


def file_sections(patch: str) -> list[FileSection]:
    """Split a git diff into one section per file, in the order it appears.

    A section carries its own header, so rendering it alone is still a valid
    diff for the reviewer and for the `diff` proof.
    """
    sections: list[FileSection] = []
    current: list[str] = []

    def flush() -> None:
        if not current:
            return
        text = "".join(current)
        parsed = change_lines(text)
        path = next(iter(parsed)) if len(parsed) == 1 else _section_path(text)
        if path is not None:
            sections.append(FileSection(path, text))

    for line in patch.splitlines(keepends=True):
        if line.startswith("diff --git ") and current:
            flush()
            current = [line]
        else:
            current.append(line)
    flush()
    return sections


def hunk_sections(section: str) -> list[str]:
    """One diff per hunk, each keeping the file header so the path survives."""
    lines = section.splitlines(keepends=True)
    start = next((index for index, line in enumerate(lines) if line.startswith("@@ ")), None)
    if start is None:
        return []
    header = "".join(lines[:start])
    hunks: list[str] = []
    current: list[str] = []
    for line in lines[start:]:
        if line.startswith("@@ ") and current:
            hunks.append(header + "".join(current))
            current = [line]
        else:
            current.append(line)
    if current:
        hunks.append(header + "".join(current))
    return hunks


def hunk_range(hunk: str) -> tuple[int, int]:
    """The new-side line range a hunk covers, 1-based and inclusive."""
    for line in hunk.splitlines():
        match = re.match(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@", line)
        if match is not None:
            start = int(match.group(1))
            count = int(match.group(2)) if match.group(2) is not None else 1
            return start, start + max(count, 1) - 1
    return 1, 1


@dataclass(frozen=True, slots=True)
class HunkParts:
    """A hunk split into its file header, its counters and its body lines."""

    header: str
    start_old: int
    start_new: int
    body: tuple[str, ...]


def hunk_parts(hunk: str) -> HunkParts:
    """Split a hunk into the parts a window needs; refuse one with no header."""
    lines = hunk.splitlines(keepends=True)
    for index, line in enumerate(lines):
        match = re.match(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@", line)
        if match is None:
            continue
        return HunkParts("".join(lines[:index]), int(match.group(1)),
                         int(match.group(3)), tuple(lines[index + 1:]))
    raise ValueError("the hunk has no @@ header")


def slice_hunk(hunk: str, start: int, end: int) -> str:
    """Re-emit the part of a hunk covering body lines [start, end).

    Splitting an added file means splitting the one hunk that carries every line,
    so the slice must still be a diff a reader and `change_lines` agree about.
    The new side is the slice's own range; the old side is wherever walking the
    lines before it left the old counter, because a hunk with context or removals
    advances both counters and the offset cannot be assumed from the index.
    """
    parts = hunk_parts(hunk)
    if not 0 <= start < end <= len(parts.body):
        raise ValueError(f"window {start}:{end} is outside a {len(parts.body)}-line hunk")
    old_line, new_line = parts.start_old, parts.start_new
    for line in parts.body[:start]:
        prefix = line[:1]
        if prefix == " ":
            old_line += 1
            new_line += 1
        elif prefix == "-":
            old_line += 1
        elif prefix == "+":
            new_line += 1
    window = parts.body[start:end]
    old_count = sum(1 for line in window if line[:1] in (" ", "-"))
    new_count = sum(1 for line in window if line[:1] in (" ", "+"))
    header = f"@@ -{old_line},{old_count} +{new_line},{new_count} @@\n"
    return parts.header + header + "".join(window)
