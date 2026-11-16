"""One parser for the unified-diff format.

Every line number, hunk body and window in this package comes from here, so the
context builder, the `diff` proof and the window slicer cannot disagree about
which lines moved.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

#: `@@ -old,count +new,count @@`; either count is omitted for a single line.
_HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")
_HEADER = re.compile(r"^(?:diff --git |--- |\+\+\+ )")
_A_PREFIX = ("a/", "b/")


def _strip(line: str) -> str | None:
    """The path a `---`/`+++` header names, or None for `/dev/null`."""
    target = line[4:].strip()
    if target == "/dev/null":
        return None
    return target[2:] if target[:2] in _A_PREFIX else target


def _path(lines: list[str]) -> str | None:
    """The path a file section is about, preferring the new side."""
    for line in lines:
        if line.startswith("+++ ") and _strip(line) is not None:
            return _strip(line)
    for line in lines:
        if line.startswith("--- ") and _strip(line) is not None:
            return _strip(line)
    for line in lines:
        if line.startswith("diff --git "):
            parts = line.split()
            if len(parts) >= 4:
                return parts[3][2:] if parts[3].startswith("b/") else parts[3]
    return None


@dataclass(frozen=True, slots=True)
class Hunk:
    """One hunk: the file header above it, its `@@` line, and its body lines.

    `header_line` is kept verbatim instead of rebuilt because git appends the
    enclosing scope to it (`@@ -1,3 +1,4 @@ def f():`), and a rebuilt header
    would silently strip that from every prompt.
    """

    file_header: str
    header_line: str
    start_old: int
    old_count: int
    start_new: int
    new_count: int
    body: tuple[str, ...]

    @property
    def text(self) -> str:
        return self.file_header + self.header_line + "".join(self.body)

    @property
    def new_range(self) -> tuple[int, int]:
        """The new-side lines this hunk covers, 1-based and inclusive."""
        return self.start_new, self.start_new + max(self.new_count, 1) - 1

    def slice(self, start: int, end: int) -> tuple[str, tuple[int, int]]:
        """The part of the hunk covering body lines [start, end), and its new range.

        Splitting an added file means splitting the one hunk that carries every
        line, so the slice must still be a diff that `change_lines` reads the way
        the whole hunk did. The old side is wherever walking the lines before the
        slice left the old counter: a hunk with context or removals advances both
        counters, so the offset cannot be assumed from the index.
        """
        if not 0 <= start < end <= len(self.body):
            raise ValueError(f"window {start}:{end} is outside a {len(self.body)}-line hunk")
        old_line, new_line = self.start_old, self.start_new
        for line in self.body[:start]:
            prefix = line[:1]
            if prefix == " ":
                old_line += 1
                new_line += 1
            elif prefix == "-":
                old_line += 1
            elif prefix == "+":
                new_line += 1
        window = self.body[start:end]
        old_count = sum(1 for line in window if line[:1] in (" ", "-"))
        new_count = sum(1 for line in window if line[:1] in (" ", "+"))
        header = f"@@ -{old_line},{old_count} +{new_line},{new_count} @@\n"
        return (self.file_header + header + "".join(window),
                (new_line, new_line + max(new_count, 1) - 1))


@dataclass(frozen=True, slots=True)
class FileSection:
    """One file's part of a unified diff, header included, parsed into hunks."""

    path: str
    text: str
    hunks: tuple[Hunk, ...]


def _hunks(lines: list[str]) -> list[Hunk]:
    """Parse one section's lines into hunks, or nothing when there is no hunk."""
    header: list[str] = []
    index = 0
    while index < len(lines) and not lines[index].startswith("@@ "):
        header.append(lines[index])
        index += 1
    file_header = "".join(header)
    hunks: list[Hunk] = []
    current: list[str] = []
    starts: tuple[int, int, int, int] | None = None
    for line in lines[index:]:
        match = _HUNK.match(line)
        if match is not None:
            if starts is not None:
                hunks.append(Hunk(file_header, current[0], *starts, tuple(current[1:])))
            starts = (int(match.group(1)),
                      int(match.group(2)) if match.group(2) is not None else 1,
                      int(match.group(3)),
                      int(match.group(4)) if match.group(4) is not None else 1)
            current = [line]
        elif starts is not None:
            current.append(line)
    if starts is not None:
        hunks.append(Hunk(file_header, current[0], *starts, tuple(current[1:])))
    return hunks


def parse_hunk(text: str) -> Hunk:
    """The first hunk of `text`; a section with no hunk is a caller error."""
    hunks = _hunks(text.splitlines(keepends=True))
    if not hunks:
        raise ValueError("the text carries no @@ hunk")
    return hunks[0]


def file_sections(patch: str) -> tuple[FileSection, ...]:
    """A git diff split per file, in order, each still a valid diff on its own."""
    blocks: list[list[str]] = []
    current: list[str] = []
    for line in patch.splitlines(keepends=True):
        if line.startswith("diff --git ") and current:
            blocks.append(current)
            current = [line]
        else:
            current.append(line)
    if current:
        blocks.append(current)

    sections: list[FileSection] = []
    for block in blocks:
        path = _path(block)
        if path is None:
            continue
        sections.append(FileSection(path, "".join(block), tuple(_hunks(block))))
    return tuple(sections)


def change_lines(diff: str) -> dict[str, tuple[set[int], set[int]]]:
    """path -> (lines added in the new file, lines removed from the old).

    A hunk's own counters decide where it ends, so a removed line that looks
    like a file header is still a removal.
    """
    changes: dict[str, tuple[set[int], set[int]]] = {}
    for section in file_sections(diff):
        if not section.hunks:
            continue
        added, removed = changes.setdefault(section.path, (set(), set()))
        for hunk in section.hunks:
            old_line, new_line = hunk.start_old, hunk.start_new
            for line in hunk.body:
                prefix = line[:1]
                if prefix == " ":
                    old_line += 1
                    new_line += 1
                elif prefix == "-":
                    removed.add(old_line)
                    old_line += 1
                elif prefix == "+":
                    added.add(new_line)
                    new_line += 1
    return changes
