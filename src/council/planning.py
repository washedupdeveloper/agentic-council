"""Turn a prepared change into prompt-sized review units.

Pure decisions except for the injected file reader: this module chooses which
files and hunks are grouped, how deep the context may be, and whether a unit
fits the caller's byte limit. It never asks a model and never writes a run.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from .changes import file_sections, hunk_range, hunk_sections
from .config import Config
from .context import Context
from .context import build as build_context
from .domain.baseline import Baseline
from .domain.scope import ScopeIgnored
from .prompt import render
from .reference import Reference
from .repo import ReviewError, Skipped, python_files
from .request import ReviewRequest


class PromptTooLarge(ReviewError):
    """The prompt is over the limit and nobody has allowed it."""

    def __init__(self, size: int, limit: int, *, declined: bool = False,
                 unit: str | None = None) -> None:
        self.size = size
        self.limit = limit
        self.unit = unit
        self.declined = declined
        tail = "Nothing was asked: proceeding was declined." if declined else "Nothing was asked."
        where = f" for {unit}" if unit else ""
        super().__init__(
            f"the prompt{where} is {size:,} bytes; the limit is {limit:,}. {tail}")


@dataclass(frozen=True, slots=True)
class Unit:
    """One prompt-sized slice of the change."""

    id: str
    files: tuple[str, ...]
    ranges: tuple[tuple[str, int, int], ...]
    patch: str
    prompt: str
    depth: int
    bytes: int
    context_digest: str


@dataclass(frozen=True, slots=True)
class Fitted:
    prompt: str
    context: Context
    depth: int
    bytes: int


@dataclass(frozen=True, slots=True)
class Prepared:
    """Everything a review and a plan share: the change, the instrument, the prompt."""

    root: Path
    config: Config
    baseline: Baseline | None
    base: str
    head: str
    patch: str
    skipped: tuple[Skipped, ...]
    scope_ignored: tuple[ScopeIgnored, ...]
    references: tuple[Reference, ...]
    prompt_file: Path
    template: str
    digest: str
    prompt: str
    prompt_bytes: int
    sliced: bool
    full_context: Context
    diff_sha256: str
    #: The profile configuration the samples were asked under: its path from the
    #: Hermes home and a digest of its bytes. Empty when it could not be read,
    #: which makes the run's instrument unknown rather than assumed.
    profile_config: str = ""
    profile_config_sha256: str = ""


@dataclass(frozen=True, slots=True)
class Plan:
    """What a review would do, without asking anyone or writing a run."""

    base: str
    head: str
    prompt_bytes: int
    prompt_limit: int
    sliced: bool
    units: tuple[Unit, ...]
    skipped: tuple[Skipped, ...]
    depth: int
    scope_ignored: tuple[ScopeIgnored, ...] = ()
    scope_include: tuple[str, ...] = ()
    scope_exclude: tuple[str, ...] = ()


def reader(root: Path) -> Callable[[str], str | None]:
    """Read a repository-relative file, refusing anything outside the checkout."""
    base = root.resolve()

    def read(rel: str) -> str | None:
        try:
            target = (base / rel).resolve()
            if not target.is_relative_to(base):
                return None
            return target.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return None

    return read


def reference_text(references: tuple[Reference, ...]) -> str:
    if not references:
        return ""
    blocks = ["## Reference (fetched by the caller; context, not evidence)"]
    blocks.extend(f"### {item.url} ({item.sha256})\n{item.text}" for item in references)
    return "\n\n".join(blocks)


def prompt_for(template: str, base: str, patch: str, root: Path, depth: int,
               references: tuple[Reference, ...]) -> Fitted:
    context = build_context(patch, reader(root), python_files(root),
                            max_depth=depth - 1)
    text = context.text
    if references:
        text = f"{text}\n\n{reference_text(references)}"
    prompt = render(template, base=base, diff=patch, context=text)
    return Fitted(prompt, context, depth, len(prompt.encode("utf-8")))


def fit(template: str, base: str, patch: str, root: Path, depth: int,
        references: tuple[Reference, ...], limit: int) -> Fitted | None:
    """The deepest context depth whose prompt fits, or None at depth zero."""
    for candidate in range(depth, -1, -1):
        fitted = prompt_for(template, base, patch, root, candidate, references)
        if fitted.bytes <= limit:
            return fitted
    return None


def build_units(template: str, base: str, patch: str, root: Path,
                request: ReviewRequest, references: tuple[Reference, ...]) -> list[Unit]:
    """File first, then hunks; deterministic, and each unit fits the budget."""
    limit = request.max_prompt_bytes
    units: list[Unit] = []

    def add(files: tuple[str, ...], ranges: tuple[tuple[str, int, int], ...],
            text: str, fitted: Fitted) -> None:
        units.append(Unit(f"unit-{len(units) + 1:03d}", files, ranges, text,
                          fitted.prompt, fitted.depth, fitted.bytes,
                          fitted.context.digest))

    for section in file_sections(patch):
        hunks = hunk_sections(section.text)
        if not hunks:
            continue
        ranges = tuple((section.path, *hunk_range(hunk)) for hunk in hunks)
        fitted = fit(template, base, section.text, root, request.context_depth,
                     references, limit)
        if fitted is not None:
            add((section.path,), ranges, section.text, fitted)
            continue
        for hunk in hunks:
            fitted = fit(template, base, hunk, root, request.context_depth,
                         references, limit)
            if fitted is None:
                smallest = prompt_for(template, base, hunk, root, 0, references)
                raise PromptTooLarge(smallest.bytes, limit, unit=section.path)
            add((section.path,), ((section.path, *hunk_range(hunk)),), hunk, fitted)
    if not units:
        raise ReviewError("the change has no reviewable file section")
    return units
