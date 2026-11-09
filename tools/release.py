"""Version and changelog check, and the bump that moves `## [Unreleased]`.

Maintainer tool, not a shipped verb:

    python tools/release.py check [--tag vX.Y.Z]
    python tools/release.py bump --version X.Y.Z [--date YYYY-MM-DD] [--dry-run]

The repository root is resolved from this file; `--repo` overrides it so the
same code can be driven against a temporary tree.
"""

from __future__ import annotations

import argparse
import re
import sys
import tomllib
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Sequence

SEMVER = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
RELEASE = re.compile(r"^## \[(\d+\.\d+\.\d+)\] — (\d{4}-\d{2}-\d{2})\s*$")
UNRELEASED = "## [Unreleased]"
PROSE = re.compile(r"[Cc]urrent release\s+\*{0,2}v(\d+\.\d+\.\d+)")
WHEEL = re.compile(r"council-(\d+\.\d+\.\d+)-py3-none-any\.whl")
CLAIMS = (PROSE, WHEEL)
VERSION_LINE = re.compile(r'(?m)^version = "([^"]+)"$')


@dataclass(frozen=True, slots=True)
class Release:
    version: str
    day: str


def default_root() -> Path:
    return Path(__file__).resolve().parent.parent


def read_version(root: Path) -> str:
    data = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    return str(data["project"]["version"])


def _version_key(version: str) -> tuple[int, int, int]:
    major, minor, patch = version.split(".")
    return int(major), int(minor), int(patch)


def split_changelog(text: str) -> tuple[str, str, str]:
    """(preamble, the Unreleased body, everything from the next release on)."""
    lines = text.splitlines(keepends=True)
    start = next((index for index, line in enumerate(lines)
                  if line.strip() == UNRELEASED), None)
    if start is None:
        raise ValueError("CHANGELOG.md has no `## [Unreleased]` section")
    end = next((index for index in range(start + 1, len(lines))
                if lines[index].startswith("## [")), len(lines))
    return "".join(lines[:start]), "".join(lines[start + 1:end]), "".join(lines[end:])


def released(text: str) -> list[Release]:
    found: list[Release] = []
    for line in text.splitlines():
        if not line.startswith("## [") or line.strip() == UNRELEASED:
            continue
        match = RELEASE.match(line)
        if match is None:
            raise ValueError(f"release heading is not `## [X.Y.Z] — YYYY-MM-DD`: {line!r}")
        found.append(Release(match.group(1), match.group(2)))
    return found


def prose_files(root: Path) -> list[Path]:
    files = [root / "README.md"]
    files.extend(sorted((root / "docs").rglob("*.md")))
    return [path for path in files
            if path.exists() and "runs" not in path.parts and path.name != "CHANGELOG.md"]


def check(root: Path, *, tag: str | None = None) -> list[str]:
    """Every reason the three copies of the version disagree."""
    errors: list[str] = []
    try:
        version = read_version(root)
    except (OSError, KeyError, tomllib.TOMLDecodeError) as exc:
        return [f"pyproject.toml: cannot read the version: {exc}"]
    if SEMVER.match(version) is None:
        errors.append(f"pyproject.toml: {version!r} is not X.Y.Z")

    try:
        text = (root / "CHANGELOG.md").read_text(encoding="utf-8")
    except OSError as exc:
        return errors + [f"CHANGELOG.md: cannot read it: {exc}"]

    headings = [line.strip() for line in text.splitlines() if line.startswith("## [")]
    if not headings or headings[0] != UNRELEASED:
        errors.append(f"CHANGELOG.md: the first section must be `{UNRELEASED}`")
    try:
        releases = released(text)
    except ValueError as exc:
        return errors + [f"CHANGELOG.md: {exc}"]

    seen: set[str] = set()
    previous: tuple[int, int, int] | None = None
    for release in releases:
        if SEMVER.match(release.version) is None:
            errors.append(f"CHANGELOG.md: {release.version!r} is not X.Y.Z")
        try:
            date.fromisoformat(release.day)
        except ValueError:
            errors.append(f"CHANGELOG.md: {release.version} has an invalid date {release.day!r}")
        if release.version in seen:
            errors.append(f"CHANGELOG.md: {release.version} appears twice")
        seen.add(release.version)
        key = _version_key(release.version) if SEMVER.match(release.version) else None
        if key is not None and previous is not None and key >= previous:
            errors.append(f"CHANGELOG.md: {release.version} is not below the release above it")
        if key is not None:
            previous = key

    if releases and releases[0].version != version:
        errors.append(f"pyproject.toml says {version}; the newest release is "
                      f"{releases[0].version}")

    for path in prose_files(root):
        text = path.read_text(encoding="utf-8")
        for pattern in CLAIMS:
            for match in pattern.finditer(text):
                if match.group(1) != version:
                    errors.append(f"{path.relative_to(root)}: claims v{match.group(1)}; "
                                  f"pyproject says {version}")

    if tag is not None:
        claimed = tag[1:] if tag.startswith("v") else tag
        if claimed != version:
            errors.append(f"tag says {claimed}; pyproject says {version}")

    return errors


def _rewrite_prose(root: Path, version: str) -> list[Path]:
    changed: list[Path] = []
    for path in prose_files(root):
        text = path.read_text(encoding="utf-8")

        def swap(match: re.Match[str]) -> str:
            return f"{match.group(0)[:match.start(1) - match.start(0)]}{version}"

        edited = text
        for pattern in CLAIMS:
            edited = pattern.sub(swap, edited)
        if edited != text:
            path.write_text(edited, encoding="utf-8", newline="\n")
            changed.append(path)
    return changed


def bump(root: Path, version: str, day: str, *, dry_run: bool = False) -> list[Path]:
    """Move Unreleased under a dated heading and rewrite every copy of the version."""
    if SEMVER.match(version) is None:
        raise ValueError(f"{version!r} is not X.Y.Z")
    current = read_version(root)
    if _version_key(version) <= _version_key(current):
        raise ValueError(f"{version} does not increase on {current}")

    changelog = root / "CHANGELOG.md"
    text = changelog.read_text(encoding="utf-8")
    head, body, rest = split_changelog(text)
    if "### " not in body:
        raise ValueError("`## [Unreleased]` has no entries: there is nothing to release")

    new_text = (head + UNRELEASED + "\n\n" + f"## [{version}] — {day}\n\n"
                + body.strip() + "\n\n" + rest.lstrip("\n"))
    project = root / "pyproject.toml"
    project_text = project.read_text(encoding="utf-8")
    new_project, count = VERSION_LINE.subn(f'version = "{version}"', project_text, count=1)
    if count != 1:
        raise ValueError("pyproject.toml has no `version = \"X.Y.Z\"` line")

    if dry_run:
        print(f"would write {changelog.relative_to(root)} (release {version}, {day})")
        print(f"would write {project.relative_to(root)} (version {version})")
        return []

    changelog.write_text(new_text, encoding="utf-8", newline="\n")
    project.write_text(new_project, encoding="utf-8", newline="\n")
    changed = [changelog, project] + _rewrite_prose(root, version)
    for path in changed:
        print(f"wrote {path.relative_to(root)}")
    print(f"tag it with: git tag -a v{version} -m \"{version}\"")
    return changed


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="release", description=__doc__)
    parser.add_argument("--repo", type=Path, default=default_root())
    sub = parser.add_subparsers(dest="command", required=True)

    verify = sub.add_parser("check", help="verify version, changelog and prose agree")
    verify.add_argument("--tag", default=None, help="a tag to compare with the build metadata")

    move = sub.add_parser("bump", help="move Unreleased under a dated heading")
    move.add_argument("--version", required=True)
    move.add_argument("--date", default=date.today().isoformat())
    move.add_argument("--dry-run", action="store_true")

    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    root = args.repo.resolve()
    try:
        if args.command == "check":
            errors = check(root, tag=args.tag)
            if errors:
                for error in errors:
                    print(f"release: {error}", file=sys.stderr)
                return 1
            print(f"release check ok: {read_version(root)}")
            return 0
        bump(root, args.version, args.date, dry_run=args.dry_run)
        return 0
    except (OSError, ValueError) as exc:
        print(f"release: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())