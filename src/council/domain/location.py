"""A finding's place: one parser for the `file:line` wire form.

The JSON contract keeps `location` as a string for compatibility, but code uses
the structured fields. A path can contain a colon; only a trailing `:<positive
integer>` is a line, so a file such as `docs/a:b.md` is no longer mis-split.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_LINE = re.compile(r"^(?P<file>.*):(?P<line>[1-9][0-9]*)$")


@dataclass(frozen=True, slots=True)
class Location:
    file: str
    line: int = 1

    @classmethod
    def parse(cls, text: str) -> Location:
        if not text:
            return cls("", 1)
        match = _LINE.match(text)
        if match is None:
            return cls(text, 1)
        return cls(match.group("file"), int(match.group("line")))

    def render(self) -> str:
        return f"{self.file}:{self.line}" if self.file else ""
