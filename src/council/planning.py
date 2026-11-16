"""Turn a prepared change into prompt-sized review units.

Pure decisions except for the injected file reader: this module chooses which
files and hunks are grouped, how deep the context may be, and whether a unit
fits the caller's byte limit. It never asks a model and never writes a run.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from .changes import file_sections, hunk_parts, hunk_range, hunk_sections, slice_hunk
from .config import Config
from .context import Context
from .context import build as build_context
from .domain.baseline import Baseline
from .domain.scope import ScopeIgnored
from .prompt import render
from .reference import Reference
from .repo import ReviewError, Skipped, python_files
from .request import ReviewRequest

#: Room reserved inside a window's budget for the `@@ … @@` line that window
#: needs, whose digits grow with the file. Over-reserving costs one line;
#: under-reserving costs a window that does not fit.
HUNK_HEADER_ROOM = 64


class PromptTooLarge(ReviewError):
    """The prompt is over the limit and nobody has allowed it.

    A file that would fit only by being split says so, with the number of windows
    and the samples that implies. The cost of saying yes is the thing a caller
    needs before deciding, and a refusal that hides it just sends them to the
    source to compute it.
    """

    def __init__(self, size: int, limit: int, *, declined: bool = False,
                 unit: str | None = None, windows: int | None = None) -> None:
        self.size = size
        self.limit = limit
        self.unit = unit
        self.declined = declined
        self.windows = windows
        where = f" for {unit}" if unit else ""
        if declined:
            tail = "Nothing was asked: proceeding was declined."
        else:
            split = ""
            if windows:
                split = (f" Split into {windows:,} windows it would be reviewed one sample "
                         "each, up to three with confirmation.")
            tail = ("Nothing was asked." + split + " Narrow the change with --base, raise the "
                    "budget with --max-prompt-bytes, split it with --window-large-files, or "
                    "allow it with --allow-large-prompt.")
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
    #: True when this unit is a line window of a hunk that could not be sent
    #: whole. A window is a fragment of one file, not a whole file.
    window: bool = False


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
    #: How many of the units are line windows, and the sample count the plan
    #: implies: one per unit, up to three when auto-sampling confirms.
    windows: int = 0
    estimated_samples: tuple[int, int] = (0, 0)


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


def window_bounds(body: tuple[str, ...], room: int) -> list[tuple[int, int]]:
    """Greedy index windows over a hunk body, each at most `room` bytes.

    Byte accounting rather than a line count: a file's lines are not uniform, and
    a window that fits only on average is a window that does not fit. A single
    line larger than the room is its own window, so the caller sees the one case
    that cannot be split rather than a silent drop.
    """
    if room <= 0 or not body:
        return []
    sizes = [len(line.encode("utf-8")) for line in body]
    bounds: list[tuple[int, int]] = []
    start = 0
    total = 0
    for index, size in enumerate(sizes):
        if total + size > room and index > start:
            bounds.append((start, index))
            start = index
            total = 0
        total += size
    if start < len(body):
        bounds.append((start, len(body)))
    return bounds


def _windowed(hunk: str, path: str, template: str, base: str, root: Path,
              request: ReviewRequest, references: tuple[Reference, ...],
              limit: int) -> list[tuple[str, tuple[int, int], Fitted]]:
    """Split one oversized hunk into windows, or refuse and say what it would cost.

    Windows are taken at depth 0. Context around a fragment makes the prompt
    larger for no gain — on a file that needs windows the enclosing function is
    already past the context builder's span limit — and depth 0 is also what
    makes the byte accounting exact instead of an estimate.
    """
    parts = hunk_parts(hunk)
    overhead = len(render(template, base=base, diff="").encode("utf-8"))
    # What a refusal quotes is the prompt it would have sent, not the diff: the
    # template is 2.6 KB before the first line of the file, so a warning that
    # counts only the diff understates a small file by half.
    size = overhead + len(hunk.encode("utf-8"))
    room = limit - overhead - len(parts.header.encode("utf-8")) - HUNK_HEADER_ROOM
    bounds = window_bounds(parts.body, room)
    if not bounds:
        # Not even one line fits beside the template: no windowing can help.
        raise PromptTooLarge(size, limit, unit=path)
    if not request.window_large_files:
        raise PromptTooLarge(size, limit, unit=path, windows=len(bounds))
    if len(bounds) > request.max_windows:
        raise ReviewError(
            f"{path} needs {len(bounds):,} windows at {limit:,} bytes and --max-windows is "
            f"{request.max_windows}: narrow the change with --base, raise --max-windows, or "
            "raise --max-prompt-bytes so each window carries more lines")
    windows: list[tuple[str, tuple[int, int], Fitted]] = []
    for start, end in bounds:
        text = slice_hunk(hunk, start, end)
        fitted = fit(template, base, text, root, 0, references, limit)
        if fitted is None:
            raise PromptTooLarge(overhead + len(text.encode("utf-8")), limit,
                                 unit=path, windows=len(bounds))
        windows.append((text, hunk_range(text), fitted))
    return windows


def build_units(template: str, base: str, patch: str, root: Path,
                request: ReviewRequest, references: tuple[Reference, ...]) -> list[Unit]:
    """File first, then hunks, then windows; deterministic, and each fits the budget.

    A hunk that is still too large is the one case with no smaller existing
    boundary: an added file is a single hunk carrying every line. There the unit
    is either refused — the default — or split into line windows the caller asked
    for, because windowing turns one prompt nobody can answer into several that
    can be, at a cost in samples the refusal states before it refuses.
    """
    limit = request.max_prompt_bytes
    units: list[Unit] = []

    def add(files: tuple[str, ...], ranges: tuple[tuple[str, int, int], ...],
            text: str, fitted: Fitted, *, window: bool = False) -> None:
        units.append(Unit(f"unit-{len(units) + 1:03d}", files, ranges, text,
                          fitted.prompt, fitted.depth, fitted.bytes,
                          fitted.context.digest, window))

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
            if fitted is not None:
                add((section.path,), ((section.path, *hunk_range(hunk)),), hunk, fitted)
                continue
            for text, span, piece in _windowed(hunk, section.path, template, base, root,
                                               request, references, limit):
                add((section.path,), ((section.path, *span),), text, piece, window=True)
    if not units:
        raise ReviewError("the change has no reviewable file section")
    return units
