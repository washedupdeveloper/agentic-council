#!/usr/bin/env python3
"""sync_to_skill.py — mirror this repo into the Hermes skill deployment."""

from __future__ import annotations

import glob
import importlib.util as _shared_util
import locale
import os
import re
import shutil
import sys
from pathlib import Path

from hermes_home import resolve as resolve_hermes_home

# `_shared` by path, like every sibling here -- see its own docstring for why a
# plain import would not be safe.
_SHARED_SPEC = _shared_util.spec_from_file_location(
    "_shared", Path(__file__).resolve().parent / "_shared.py")
assert _SHARED_SPEC is not None and _SHARED_SPEC.loader is not None, "_shared.py"
_shared = _shared_util.module_from_spec(_SHARED_SPEC)
_SHARED_SPEC.loader.exec_module(_shared)

ROOT = Path(__file__).resolve().parent.parent

# --help is byte-identical to what the shell version printed.
USAGE = """\
Sync the repo's scripts + bot definitions + rubrics + tests + the council
SKILL.md INTO the skill LIBRARY — the source of truth — so the skill the agent
loads never drifts from the repo that authors it.

The library is MOUNTED read-only via `skills.external_dirs`, not copied into
~/.hermes/skills/. So this script resolves its destination by ASKING HERMES
where that mount is, and falls back to the installed location only when no
mount is configured — with a warning, because a copy there is SHADOWED by any
mount (local skills outrank external ones), which is how two copies silently
diverge: the agent loads one while the repo updates the other.

No absolute paths: the destination comes from the live config, so the same
script works on Windows, macOS, Linux and WSL2.

The council skill's own SKILL.md is version-controlled at skills/council/SKILL.md
and copied in here. It used to be authored in place at the install location with
no repo source — orphaned, so losing the skill directory lost the documentation.

Usage:
  council setup skill           # install into the mounted library
  council setup skill --check   # report drift, change nothing (exit 1 if any)
  DEST_SKILL=/path/to/skills/.../council council setup skill
"""

# The shell's globals: the resolved destination, --check, and the drift flag.
DEST = ""
CHECK_ONLY = False
DRIFT = False

# What makes the installed skill able to build its own toolchain. See main().
FLAKE_FILES = ("flake.nix", "flake.lock")


def hermes_run(args: list[str]) -> tuple[int, str]:
    """A `hermes ...` call's exit status and stdout; stderr dropped."""
    return _shared.hermes_run(args)


def sort_names(names: list[str]) -> list[str]:
    """bash globs and `ls` sort by locale collation, not by code point."""
    return sorted(names, key=locale.strxfrm)


def resolve_mounted_skills_root() -> str:
    """The skills root Hermes mounts via skills.external_dirs, or "" when none."""
    if not shutil.which("hermes"):
        return ""
    # Asked of Hermes, so the ~ expansion matches what the loader does.
    rc, out = hermes_run(["hermes", "config", "get", "skills.external_dirs"])
    if rc != 0:
        return ""
    raw = out.replace("\r", "")
    # A list prints one "  - <path>" per entry; a scalar prints the bare path.
    entry = ""
    for line in raw.splitlines():
        match = re.match(r"^\s*-\s*(.*)$", line)
        if match:
            entry = match.group(1)
            break
    if not entry:
        for line in raw.splitlines():
            if line.strip():
                entry = line
                break
        if not entry or entry.startswith("-"):
            return ""
    if entry.startswith("~/"):
        entry = str(Path.home()) + "/" + entry[2:]
    elif entry == "~":
        entry = str(Path.home())
    elif not (entry.startswith("/") or re.match(r"^[A-Za-z]:[/\\]", entry)):
        entry = resolve_hermes_home() + "/" + entry  # Hermes resolves against HERMES_HOME
    return entry if Path(entry).is_dir() else ""


def warn_unmounted() -> None:
    print("council setup skill: no skills.external_dirs mount is configured, so this falls",
          file=sys.stderr)
    print("  back to the installed dir. A copy there is SHADOWED the moment a mount is",
          file=sys.stderr)
    print("  added (local beats external) and the two silently diverge. Prefer:",
          file=sys.stderr)
    print("    hermes config set skills.external_dirs '[\"<library>/skills\"]'",
          file=sys.stderr)


def lf_bytes(data: bytes) -> bytes:
    """`sed 's/\\r$//'`: drop one trailing CR per line, and terminate the last."""
    lines = data.split(b"\n")
    if lines and lines[-1] == b"":
        lines.pop()
    return b"".join((line[:-1] if line.endswith(b"\r") else line) + b"\n"
                    for line in lines)


def find_files(root: str) -> list[str]:
    """Every file under root, like `find root -type f`: readdir order, pre-order."""
    found: list[str] = []
    with os.scandir(root) as entries:
        for entry in entries:
            if entry.is_dir(follow_symlinks=False):
                found.extend(find_files(entry.path))
            elif entry.is_file(follow_symlinks=False):
                found.append(entry.path)
    return found


def remove_empty_dirs(root: str) -> None:
    """`find root -mindepth 1 -type d -empty -delete`, bottom-up."""
    for dirpath, dirnames, _files in os.walk(root, topdown=False):
        for name in dirnames:
            try:
                os.rmdir(os.path.join(dirpath, name))
            except OSError:
                pass


def rel_to_dest(path: str) -> str:
    """A destination path as the reports print it."""
    prefix = DEST + "/"
    return path[len(prefix):] if path.startswith(prefix) else path


def is_our_destination(dest: str) -> bool:
    """True when *dest* is absent, empty, or already the council skill.

    DEST_SKILL is caller-supplied and feeds prune_tree(), which DELETES whatever the
    repo does not have. Pointed at a skills-library root rather than the council
    directory, it removed files belonging to another skill -- reproduced. So a
    non-empty destination has to prove it is ours before anything is removed.
    """
    if not os.path.isdir(dest):
        return True
    try:
        if not os.listdir(dest):
            return True
    except OSError:
        return False
    marker = os.path.join(dest, "SKILL.md")
    if not os.path.isfile(marker):
        return False
    try:
        head = Path(marker).read_text(encoding="utf-8", errors="replace")[:400]
    except OSError:
        return False
    return "name: council" in head


def place(src: str, dst: str) -> None:
    """Copy src as LF text, or compare it; --check sets DRIFT on a difference."""
    global DRIFT
    if CHECK_ONLY:
        same = os.path.isfile(dst) and (
            lf_bytes(Path(src).read_bytes()) == lf_bytes(Path(dst).read_bytes()))
        if not same:
            print("  DRIFT  " + rel_to_dest(dst))
            DRIFT = True
        return
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    Path(dst).write_bytes(lf_bytes(Path(src).read_bytes()))


def prune_tree(src: str, dst: str) -> None:
    """Mirror, don't merge: drop what the repo no longer has, or report it.

    A removal is PRINTED either way. It used to be silent in the writing case,
    which meant a sync run from a tree that carries fewer modules than the repo
    deleted the difference and said nothing -- the deployment lost files and the
    only evidence was that they were gone.
    """
    global DRIFT
    if not os.path.isdir(dst):
        return
    for path in find_files(dst):
        rel = os.path.relpath(path, dst)
        if os.path.exists(os.path.join(src, rel)):
            continue
        if CHECK_ONLY:
            print("  EXTRA  " + rel_to_dest(path) + "  (deleted in the repo)")
            DRIFT = True
        else:
            print("  REMOVED  " + rel_to_dest(path) + "  (not in the source)")
            os.remove(path)
    if not CHECK_ONLY:
        remove_empty_dirs(dst)


def ls_line(path: str) -> str:
    """`ls path | tr '\\n' ' '`: visible names, sorted, each followed by a space."""
    try:
        names = sort_names([n for n in os.listdir(path) if not n.startswith(".")])
    except OSError:
        return ""
    return "".join(f"{name} " for name in names)


def main(argv: list[str] | None = None) -> int:
    global DEST, CHECK_ONLY, DRIFT

    argv = sys.argv[1:] if argv is None else list(argv)
    for arg in argv:
        if arg == "--check":
            CHECK_ONLY = True
        elif arg in ("-h", "--help"):
            sys.stdout.write(USAGE)
            return 0
        else:
            print(f"council setup skill: unknown argument: {arg}", file=sys.stderr)
            return 2

    try:
        locale.setlocale(locale.LC_COLLATE, "")
    except locale.Error:
        pass

    root = str(ROOT)
    dest = os.environ.get("DEST_SKILL") or ""
    note = "explicit DEST_SKILL"
    if not dest:
        mounted = resolve_mounted_skills_root()
        if mounted:
            dest = mounted + "/autonomous-ai-agents/council"
            note = f"mounted library ({mounted})"
        else:
            dest = resolve_hermes_home() + "/skills/autonomous-ai-agents/council"
            note = "installed skills dir — NOT MOUNTED"
            warn_unmounted()
    DEST = dest

    if not is_our_destination(DEST):
        print(f"council setup skill: refusing to sync into {DEST}\n"
              f"  it is a non-empty directory that is not the council skill, and a sync\n"
              f"  PRUNES what this repo does not have. Point DEST_SKILL at the council\n"
              f"  directory itself (the one holding SKILL.md).", file=sys.stderr)
        return 2

    if CHECK_ONLY:
        print(f"Checking {DEST} against {root} (no changes)")
    else:
        print(f"Syncing {root} -> {DEST}")
        print(f"  destination: {note}")
        for sub in ("scripts", "tests", "assets/bots", "assets/rubrics"):
            os.makedirs(f"{DEST}/{sub}", exist_ok=True)

    # Every runtime script the framework ships, so a new one is never forgotten.
    for pattern in ("*.py",):
        for src in sort_names(glob.glob(f"{glob.escape(root)}/scripts/{pattern}")):
            name = os.path.basename(src)
            if os.path.isfile(src) and name != "sync_to_skill.py":  # the copier never ships
                place(src, f"{DEST}/scripts/{name}")

    for src in sort_names(glob.glob(f"{glob.escape(root)}/tests/*.py")):
        if os.path.isfile(src):
            place(src, f"{DEST}/tests/{os.path.basename(src)}")

    # The golden suite's fixture DATA: test_golden.py cannot run without it.
    golden = f"{root}/tests/golden"
    if os.path.isdir(golden):
        for src in find_files(golden):
            place(src, f"{DEST}/tests/golden/{os.path.relpath(src, golden)}")

    # Bytecode caches are host-specific and meaningless. `.pytest_cache` too: it
    # was reaching the deployment and is a cache, not content.
    if not CHECK_ONLY:
        for cache in (f"{DEST}/scripts/__pycache__", f"{DEST}/tests/__pycache__",
                      f"{DEST}/.pytest_cache", f"{DEST}/tests/.pytest_cache"):
            shutil.rmtree(cache, ignore_errors=True)

    # The pinned toolchain definition, so a machine with only the skill can build
    # it (`toolchain.py`'s fallback). NOT optional: without these the deployment
    # cannot resolve a toolchain on its own.
    #
    # This used to be `if os.path.isfile(src): place(...)` with no else, and a sync
    # run from a nix framework tree -- which by design carries no flake.nix -- then
    # skipped BOTH files silently. The deployment's flake.nix stayed at whatever it
    # was, a user who ran `nix build <skill>#toolchain` got the old toolchain, and
    # nothing anywhere said so. Measured: a deployment 489 lines and two major
    # changes behind, reporting "in sync" apart from one line of drift.
    #
    # The source comes from REVIEW_COUNCIL_FLAKE_DIR when the launcher set it (the
    # nix app, the container), else from the checkout beside us.
    flake_dir = os.environ.get("REVIEW_COUNCIL_FLAKE_DIR") or root
    missing = [n for n in FLAKE_FILES if not os.path.isfile(os.path.join(flake_dir, n))]
    if missing:
        print(f"council setup skill: cannot install {', '.join(missing)} — not found in\n"
              f"  {flake_dir}\n"
              f"  Without them the installed skill cannot build its own toolchain.\n"
              f"  Run this from a checkout of the repository, or through the council's\n"
              f"  own launcher, which passes REVIEW_COUNCIL_FLAKE_DIR.", file=sys.stderr)
        return 2
    for name in FLAKE_FILES:
        place(os.path.join(flake_dir, name), f"{DEST}/{name}")

    # The flake MODULES, which the flake.nix just installed IMPORTS. A flake's
    # `imports` are eager, so without these the deployed flake evaluates to NOTHING --
    # `.#toolchain` included, which is the one thing this install exists to provide.
    # The same silent-skip trap as the two files above, one level down: the file
    # installs, the flake looks complete, and nothing resolves.
    nix_dir = Path(flake_dir, "nix")
    if not nix_dir.is_dir():
        print(f"council setup skill: cannot install nix/ -- not found in\n"
              f"  {flake_dir}\n"
              f"  The flake.nix it installs imports these modules, so without them the\n"
              f"  installed flake evaluates to nothing. Run this from a checkout of the\n"
              f"  repository, or through the council's own launcher.", file=sys.stderr)
        return 2
    for entry in sort_names([n for n in os.listdir(nix_dir) if not n.startswith(".")]):
        src = nix_dir / entry
        if src.is_file():
            place(str(src), f"{DEST}/nix/{entry}")

    # Without these the gate falls back to the uncalibrated count-based curve.
    for name in ("calibration.json", "eval-baseline.json"):
        src = f"{root}/scripts/{name}"
        if os.path.isfile(src):
            place(src, f"{DEST}/scripts/{name}")

    bots = Path(root, "bots")
    if bots.is_dir():
        names = [n for n in os.listdir(bots)
                 if not n.startswith(".") and (bots / n).is_dir()]
        for name in sort_names(names):
            for fname in ("SOUL.md", "profile.yaml", "bot.yaml"):
                if (bots / name / fname).is_file():
                    place(str(bots / name / fname), f"{DEST}/assets/bots/{name}/{fname}")

    # The six rubric skills -> assets/rubrics/<name>/SKILL.md.
    skills = Path(root, "skills")
    if skills.is_dir():
        names = [n for n in os.listdir(skills)
                 if not n.startswith(".") and (skills / n).is_dir()]
        for name in sort_names(names):
            if name != "council" and (skills / name / "SKILL.md").is_file():
                place(str(skills / name / "SKILL.md"),
                      f"{DEST}/assets/rubrics/{name}/SKILL.md")

    # The council skill's own SKILL.md — the /council command documentation.
    council = f"{root}/skills/council/SKILL.md"
    if os.path.isfile(council):
        place(council, f"{DEST}/SKILL.md")

    # AFTER the copies: a file added this run must not be pruned before it lands.
    prune_tree(f"{root}/scripts", f"{DEST}/scripts")
    prune_tree(f"{root}/tests", f"{DEST}/tests")
    prune_tree(f"{root}/bots", f"{DEST}/assets/bots")
    prune_tree(f"{root}/skills", f"{DEST}/assets/rubrics")

    if CHECK_ONLY:
        if DRIFT:
            print(f"council setup skill: {DEST} has drifted from {root}; run without --check")
            return 1
        print("  in sync")
        return 0

    for label, sub in (("scripts/", "scripts"), ("tests/", "tests"),
                       ("bots/", "assets/bots"), ("rubrics/", "assets/rubrics")):
        listing = ls_line(f"{DEST}/{sub}")
        print(f"  {label:<8}  ->  {listing}")
    print("  SKILL.md  ->  synced from skills/council/SKILL.md")
    return 0


if __name__ == "__main__":
    # Not a program: reached through `council <verb>`. See council.py.
    from council import require_dispatch

    require_dispatch("setup skill")
    sys.exit(main())
