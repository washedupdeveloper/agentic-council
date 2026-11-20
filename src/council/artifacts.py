"""Local evidence attached to a kept run, beside its verdict.

The reviewer never reads these files. A screenshot is stored as bytes and named
by its hash, so a later reader can verify that the image still matches the
manifest without asking a model what the image means.

The manifest holds relative paths. Moving the run directory keeps the links
valid; moving or deleting one screenshot is the user's business, not a reason
for `council evidence list` to fail.
"""

from __future__ import annotations

import hashlib
import json
import mimetypes
import os
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from pathlib import PurePosixPath

from . import paths
from .domain.run_id import validate_run_id
from .repo import ReviewError

ARTIFACTS = "artifacts"
MANIFEST = "artifacts.json"
FORMAT = 1
_SHA256 = re.compile(r"[0-9a-f]{64}")
_SAFE_SUFFIX = re.compile(r"\.[a-z0-9]{1,10}")


@dataclass(frozen=True, slots=True)
class Artifact:
    """One file, its hash, and the human label that links to it."""

    path: str
    sha256: str
    bytes: int
    media_type: str
    label: str
    captured_at: str

    def payload(self, run_dir: Path) -> dict[str, object]:
        target = run_dir / self.path
        return {
            "path": self.path,
            "sha256": self.sha256,
            "bytes": self.bytes,
            "media_type": self.media_type,
            "label": self.label,
            "captured_at": self.captured_at,
            "link": link(run_dir, self),
            "missing": not target.is_file(),
        }


def _guard_run(run_dir: Path) -> None:
    if run_dir.is_symlink():
        raise ReviewError(f"{run_dir} is a symlink: a run must not point outside its state directory")
    if not run_dir.is_dir():
        raise ReviewError(f"run directory {run_dir} does not exist")


def _guard_artifacts(run_dir: Path) -> Path:
    directory = run_dir / ARTIFACTS
    if directory.is_symlink():
        raise ReviewError(f"{directory} is a symlink: refusing to write outside the run")
    if directory.exists() and not directory.is_dir():
        raise ReviewError(f"{directory} is not a directory")
    return directory


def _manifest_path(run_dir: Path) -> Path:
    path = run_dir / MANIFEST
    if path.is_symlink():
        raise ReviewError(f"{path} is a symlink: refusing to write outside the run")
    return path


def _artifact(raw: object, run_dir: Path) -> Artifact:
    if not isinstance(raw, dict):
        raise ReviewError(f"{run_dir / MANIFEST} has a malformed artifact entry")
    path = raw.get("path")
    sha = raw.get("sha256")
    size = raw.get("bytes")
    media_type = raw.get("media_type")
    label = raw.get("label")
    captured = raw.get("captured_at")
    if (not isinstance(path, str) or not isinstance(sha, str)
            or not isinstance(media_type, str) or not isinstance(label, str)
            or not isinstance(captured, str)):
        raise ReviewError(f"{run_dir / MANIFEST} has a malformed artifact entry")
    if not isinstance(size, int) or isinstance(size, bool) or size < 0:
        raise ReviewError(f"{run_dir / MANIFEST} has a malformed artifact size")
    if not _SHA256.fullmatch(sha):
        raise ReviewError(f"{run_dir / MANIFEST} has a malformed artifact hash")
    relative = PurePosixPath(path)
    if ("\\" in path or relative.is_absolute()
            or len(relative.parts) < 2 or relative.parts[0] != ARTIFACTS
            or ".." in relative.parts):
        raise ReviewError(f"{run_dir / MANIFEST} names an artifact outside {ARTIFACTS}/")
    return Artifact(relative.as_posix(), sha, size, media_type, label, captured)


def read(run_dir: Path) -> tuple[Artifact, ...]:
    """Read the sidecar manifest. A missing manifest means no artifacts."""
    _guard_run(run_dir)
    path = _manifest_path(run_dir)
    if not path.exists():
        return ()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ReviewError(f"cannot read {path}: {exc}") from exc
    if not isinstance(raw, dict) or raw.get("format") != FORMAT:
        raise ReviewError(f"{path} is not an artifacts manifest format {FORMAT}")
    rows = raw.get("artifacts")
    if not isinstance(rows, list):
        raise ReviewError(f"{path} has no artifacts list")
    return tuple(_artifact(row, run_dir) for row in rows)


def _slug(source: Path) -> str:
    stem = re.sub(r"[^A-Za-z0-9._-]+", "-", source.stem).strip("._-")
    return (stem or "evidence")[:48]


def _media_type(source: Path) -> str:
    return mimetypes.guess_type(source.name)[0] or "application/octet-stream"


def _name(source: Path, digest: str) -> str:
    suffix = source.suffix.lower()
    if not _SAFE_SUFFIX.fullmatch(suffix):
        suffix = ".bin"
    return f"{digest[:16]}-{_slug(source)}{suffix}"


def _write_manifest(run_dir: Path, entries: list[Artifact]) -> None:
    path = _manifest_path(run_dir)
    payload = {
        "format": FORMAT,
        "run": run_dir.name,
        "artifacts": [
            {
                "path": entry.path,
                "sha256": entry.sha256,
                "bytes": entry.bytes,
                "media_type": entry.media_type,
                "label": entry.label,
                "captured_at": entry.captured_at,
            }
            for entry in entries
        ],
    }
    temporary = path.with_name(path.name + ".tmp")
    if temporary.is_symlink():
        raise ReviewError(f"{temporary} is a symlink: refusing to write outside the run")
    try:
        temporary.write_text(json.dumps(payload, indent=2) + "\n",
                              encoding="utf-8", newline="\n")
        os.replace(temporary, path)
    except OSError as exc:
        raise ReviewError(f"cannot write {path}: {exc}") from exc
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass


def add(run_dir: Path, sources: list[Path], *, label: str = "",
        captured_at: str | None = None) -> tuple[Artifact, ...]:
    """Copy files into the run and record their relative links.

    The same bytes are stored once. The manifest is written last, so a failed
    copy cannot make a file that is not there look like recorded evidence.
    """
    _guard_run(run_dir)
    entries = list(read(run_dir))
    captured = captured_at or datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
    prepared: list[tuple[Path, bytes, str]] = []
    for source in sources:
        source = Path(source)
        if source.is_symlink():
            raise ReviewError(f"{source} is a symlink: refusing to copy a linked file")
        if not source.is_file():
            raise ReviewError(f"{source} is not a regular file")
        try:
            data = source.read_bytes()
        except OSError as exc:
            raise ReviewError(f"cannot read {source}: {exc}") from exc
        prepared.append((source, data, hashlib.sha256(data).hexdigest()))

    directory = _guard_artifacts(run_dir)
    try:
        directory.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise ReviewError(f"cannot create {directory}: {exc}") from exc

    by_hash = {entry.sha256: entry for entry in entries}
    result: list[Artifact] = []
    for source, data, digest in prepared:
        existing = by_hash.get(digest)
        if existing is not None:
            target = run_dir / existing.path
            if target.is_symlink():
                raise ReviewError(f"{target} is a symlink: refusing to write outside the run")
            if not target.exists():
                try:
                    target.write_bytes(data)
                except OSError as exc:
                    raise ReviewError(f"cannot restore {target}: {exc}") from exc
            result.append(existing)
            continue
        name = _name(source, digest)
        target = directory / name
        if target.is_symlink():
            raise ReviewError(f"{target} is a symlink: refusing to write outside the run")
        if target.exists():
            try:
                same = target.read_bytes() == data
            except OSError as exc:
                raise ReviewError(f"cannot read {target}: {exc}") from exc
            if not same:
                raise ReviewError(f"{target} exists with different contents")
        else:
            try:
                target.write_bytes(data)
            except OSError as exc:
                raise ReviewError(f"cannot write {target}: {exc}") from exc
        entry = Artifact(f"{ARTIFACTS}/{name}", digest, len(data),
                         _media_type(source), label.strip() or source.stem, captured)
        entries.append(entry)
        by_hash[digest] = entry
        result.append(entry)

    _write_manifest(run_dir, entries)
    return tuple(result)


def escape_markdown(text: str) -> str:
    """Keep a label from turning into markup; labels are user input."""
    return (text.replace("\\", "\\\\").replace("[", "\\[").replace("]", "\\]")
            .replace("\n", " ").replace("\r", " "))


def link(run_dir: Path, artifact: Artifact) -> str:
    """An absolute file link; it may point at a file the user has moved."""
    try:
        return (run_dir / artifact.path).resolve().as_uri()
    except (OSError, RuntimeError, ValueError):
        return ""


def markdown(run_dir: Path, artifact: Artifact) -> str:
    label = escape_markdown(artifact.label or Path(artifact.path).name)
    return f"[{label}]({link(run_dir, artifact)})"


def resolve_run(run_id: str, *, repo: Path = Path("."),
                state_root: Path | None = None) -> Path:
    """Find a kept run by id in a checkout, an explicit root, or the cache."""
    try:
        validated = validate_run_id(run_id)
    except ValueError as exc:
        raise ReviewError(str(exc)) from exc
    candidates: list[Path] = []
    if state_root is not None:
        candidates.append(state_root / validated)
    try:
        candidates.append(paths.state_root(repo) / validated)
    except (OSError, ValueError) as exc:
        raise ReviewError(str(exc)) from exc
    candidates.append(paths.cache_runs_root() / validated)
    seen: set[Path] = set()
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        if candidate.is_symlink():
            raise ReviewError(f"{candidate} is a symlink: refusing to use a linked run")
        if candidate.is_dir():
            return candidate.resolve()
    looked = ", ".join(str(candidate) for candidate in candidates)
    raise ReviewError(f"run {validated!r} not found; looked in {looked}")
