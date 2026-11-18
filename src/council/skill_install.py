"""Install skills from a library into an agent's skills directory.

A *library* is a directory that carries ``library/contract.json`` and lays its
skills out as ``skills/<category>/<name>/SKILL.md``. A *destination* is a
directory laid out as ``<name>/SKILL.md`` — which is what an agent reads.

Nothing here names an agent. ``--dest`` and ``$SKILLS_DIR`` are the neutral
path; ``--agent`` only fills the destination from a table of conventional
locations, and refuses to invent one that is not already on disk. The same verb
therefore serves Hermes today and whatever replaces it later, and a library
shared with someone running a different agent needs no second code path.

Library resolution is by structure — the contract file, never a directory name —
so a library that is renamed or vendored elsewhere is still found, and an
unrelated directory that happens to share its name is not.
"""

from __future__ import annotations

import os
import shutil
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import NamedTuple

__all__ = ["AGENT_DIRS", "Skill", "SkillSetupError", "catalog", "install",
           "resolve_destination", "resolve_library", "run"]

#: What makes a directory a library, and what is not a skill inside one.
CONTRACT = Path("library") / "contract.json"
SUPPORT_DIRS = ("references", "templates", "assets", "scripts", "examples")
_IGNORE = shutil.ignore_patterns("__pycache__", ".pytest_cache", ".ruff_cache", ".mypy_cache")

#: Conventional skills directories, most specific first. `$NAME` is read from the
#: environment and skipped when unset, so an agent that is not installed simply does
#: not match. This table is convenience, not the design: `--dest` and `$SKILLS_DIR`
#: never consult it.
AGENT_DIRS: dict[str, tuple[str, ...]] = {
    "hermes": ("$HERMES_HOME/skills", "~/.hermes/skills"),
    "claude": ("~/.claude/skills",),
    "codex": ("~/.codex/skills",),
    "opencode": ("~/.config/opencode/skills",),
    "cursor": ("~/.cursor/skills",),
    "gemini": ("~/.gemini/skills",),
}


class SkillSetupError(Exception):
    """A refusal: the caller prints it and exits non-zero."""


class Skill(NamedTuple):
    name: str
    description: str
    path: Path


def _expand(raw: str, env: Mapping[str, str], home: Path) -> Path | None:
    """`$VAR/rest` or `~/rest` as a path; None when the variable is unset."""
    if raw.startswith("$"):
        name, _, rest = raw[1:].partition("/")
        base = env.get(name)
        return Path(base) / rest if base else None
    if raw in ("~", "~/"):
        return home
    if raw.startswith("~/"):
        return home / raw[2:]
    return Path(raw)


def _has_contract(root: Path) -> bool:
    return (root / CONTRACT).is_file()


def resolve_library(explicit: Path | None, *, env: Mapping[str, str],
                    start: Path) -> Path:
    """``--library``, else ``$SKILLS_LIBRARY``, else the nearest ancestor with a contract."""
    if explicit is not None:
        if not _has_contract(explicit):
            raise SkillSetupError(
                f"--library {explicit} is not a skill library (no {CONTRACT})")
        return explicit
    configured = env.get("SKILLS_LIBRARY")
    if configured:
        root = Path(configured).expanduser()
        if not _has_contract(root):
            raise SkillSetupError(
                f"$SKILLS_LIBRARY is {root}, which is not a skill library (no {CONTRACT})")
        return root
    for ancestor in (start, *start.parents):
        if _has_contract(ancestor):
            return ancestor
    raise SkillSetupError(
        "no skill library found: pass --library DIR or set $SKILLS_LIBRARY")


def _description(path: Path) -> str:
    """The `description:` line of a SKILL.md frontmatter, or an empty string."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    if not text.startswith("---"):
        return ""
    end = text.find("\n---", 3)
    head = text[3:end] if end != -1 else ""
    for line in head.splitlines():
        key, sep, value = line.partition(":")
        if sep and key.strip() == "description":
            return value.strip().strip("\"'")
    return ""


def catalog(library: Path) -> list[Skill]:
    """Every catalog skill in the library, sorted by name.

    A SKILL.md inside a support directory is a file *within* a skill, not a skill:
    the layout decides, exactly as it does for the library's own gate.
    """
    skills_root = library / "skills"
    if not skills_root.is_dir():
        raise SkillSetupError(f"{library} has no skills/ directory")
    found: list[Skill] = []
    for path in sorted(skills_root.rglob("SKILL.md")):
        parts = path.relative_to(skills_root).parts
        if len(parts) < 3 or set(parts[1:-1]) & set(SUPPORT_DIRS):
            continue
        found.append(Skill(path.parent.name, _description(path), path.parent))
    return sorted(found, key=lambda skill: skill.name)


def resolve_destination(explicit: Path | None, agent: str | None, *,
                        env: Mapping[str, str], home: Path) -> Path:
    """``--dest``, else ``$SKILLS_DIR``, else the named agent's existing directory."""
    if explicit is not None:
        return explicit
    configured = env.get("SKILLS_DIR")
    if configured:
        return Path(configured).expanduser()
    if agent:
        candidates = AGENT_DIRS.get(agent)
        if candidates is None:
            raise SkillSetupError(
                f"unknown agent {agent!r}; known: {', '.join(sorted(AGENT_DIRS))}")
        resolved = [path for path in (_expand(raw, env, home) for raw in candidates)
                    if path is not None]
        for path in resolved:
            if path.is_dir():
                return path
        raise SkillSetupError(
            f"no skills directory on this machine for {agent!r} (looked in "
            f"{', '.join(str(p) for p in resolved)}); pass --dest DIR")
    raise SkillSetupError(
        "no destination: pass --dest DIR, set $SKILLS_DIR, or name --agent")


def _same_tree(left: Path, right: Path) -> bool:
    """True when two skill directories hold the same files with the same bytes."""
    left_files = {p.relative_to(left).as_posix(): p for p in left.rglob("*") if p.is_file()}
    right_files = {p.relative_to(right).as_posix(): p for p in right.rglob("*") if p.is_file()}
    if left_files.keys() != right_files.keys():
        return False
    return all(left_files[rel].read_bytes() == right_files[rel].read_bytes()
               for rel in left_files)


def install(names: Sequence[str], library: Path, dest: Path, *, force: bool,
            dry_run: bool) -> list[str]:
    """Copy each named skill into ``dest``; never overwrite unless ``force``."""
    by_name = {skill.name: skill for skill in catalog(library)}
    unknown = [name for name in names if name not in by_name]
    if unknown:
        raise SkillSetupError(
            f"the library has no skill named {', '.join(sorted(set(unknown)))}")
    lines: list[str] = []
    for name in names:
        source = by_name[name].path
        target = dest / name
        if target.exists():
            if _same_tree(source, target):
                lines.append(f"unchanged {name}")
                continue
            if not force:
                raise SkillSetupError(
                    f"{target} exists and differs; pass --force to replace it")
            verb = "would replace" if dry_run else "replaced"
            if not dry_run:
                shutil.rmtree(target)
        else:
            verb = "would install" if dry_run else "installed"
        if not dry_run:
            dest.mkdir(parents=True, exist_ok=True)
            shutil.copytree(source, target, ignore=_IGNORE)
        lines.append(f"{verb} {name} -> {target}")
    return lines


def run(args: object, *, env: Mapping[str, str] | None = None,
        home: Path | None = None, cwd: Path | None = None) -> int:
    """The `setup skill` verb: list, or install, and print one line per skill."""
    env = dict(os.environ) if env is None else env
    home = Path.home() if home is None else home
    cwd = Path.cwd() if cwd is None else cwd

    library = resolve_library(getattr(args, "library", None), env=env, start=cwd)
    skills = catalog(library)

    if getattr(args, "list", False):
        for skill in skills:
            print(f"{skill.name}\t{skill.description}")
        return 0

    names = list(getattr(args, "names", ()) or ())
    if not names:
        raise SkillSetupError(
            f"{library} holds {len(skills)} skills; name at least one, or pass --list")
    dest = resolve_destination(getattr(args, "dest", None), getattr(args, "agent", None),
                               env=env, home=home)
    for line in install(names, library, dest,
                        force=bool(getattr(args, "force", False)),
                        dry_run=bool(getattr(args, "dry_run", False))):
        print(line)
    return 0
