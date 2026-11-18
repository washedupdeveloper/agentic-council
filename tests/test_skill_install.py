"""`council setup skill` installs from a library without being told which agent.

Every test here builds a library that carries nothing but a contract and a couple of
SKILL.md files, because that is the whole contract: a directory that looks like a
library is one. The destination is the same shape — a directory that will hold
`<name>/SKILL.md` — so none of these tests has an agent in it.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pytest

from council import skill_install
from council.skill_install import SkillSetupError


def library(root: Path, *names: str) -> Path:
    (root / "library").mkdir(parents=True, exist_ok=True)
    (root / "library" / "contract.json").write_text("{}\n", encoding="utf-8")
    for name in names:
        skill = root / "skills" / "alpha" / name
        skill.mkdir(parents=True, exist_ok=True)
        (skill / "SKILL.md").write_text(
            f"---\nname: {name}\ndescription: Use when {name}.\n---\n\n# {name}\n",
            encoding="utf-8")
        (skill / "references").mkdir()
        (skill / "references" / "depth.md").write_text("depth\n", encoding="utf-8")
    return root


def args(**overrides: object) -> argparse.Namespace:
    base = dict(names=[], library=None, dest=None, agent=None, list=False,
                force=False, dry_run=False)
    base.update(overrides)
    return argparse.Namespace(**base)


def call(tmp: Path, **overrides: object) -> int:
    lib = overrides.pop("library_root", tmp / "lib")
    return skill_install.run(args(library=lib, **overrides), env={}, home=tmp / "home",
                             cwd=tmp)


def test_installs_into_a_destination_with_no_agent_named(tmp_path: Path,
                                                         capsys: pytest.CaptureFixture[str]) -> None:
    lib = library(tmp_path / "lib", "probe")
    dest = tmp_path / "skills"
    assert call(tmp_path, library_root=lib, names=["probe"], dest=dest) == 0
    assert (dest / "probe" / "SKILL.md").is_file()
    assert (dest / "probe" / "references" / "depth.md").is_file()
    assert "installed probe" in capsys.readouterr().out


def test_a_second_identical_run_reports_unchanged(tmp_path: Path,
                                                  capsys: pytest.CaptureFixture[str]) -> None:
    lib = library(tmp_path / "lib", "probe")
    dest = tmp_path / "skills"
    call(tmp_path, library_root=lib, names=["probe"], dest=dest)
    capsys.readouterr()
    assert call(tmp_path, library_root=lib, names=["probe"], dest=dest) == 0
    assert "unchanged probe" in capsys.readouterr().out


def test_a_differing_skill_is_refused_without_force(tmp_path: Path,
                                                    capsys: pytest.CaptureFixture[str]) -> None:
    lib = library(tmp_path / "lib", "probe")
    dest = tmp_path / "skills"
    call(tmp_path, library_root=lib, names=["probe"], dest=dest)
    (dest / "probe" / "SKILL.md").write_text("edited by hand\n", encoding="utf-8")
    with pytest.raises(SkillSetupError) as raised:
        call(tmp_path, library_root=lib, names=["probe"], dest=dest)
    assert "--force" in str(raised.value)
    assert (dest / "probe" / "SKILL.md").read_text(encoding="utf-8") == "edited by hand\n"


def test_force_replaces(tmp_path: Path) -> None:
    lib = library(tmp_path / "lib", "probe")
    dest = tmp_path / "skills"
    call(tmp_path, library_root=lib, names=["probe"], dest=dest)
    (dest / "probe" / "SKILL.md").write_text("edited by hand\n", encoding="utf-8")
    assert call(tmp_path, library_root=lib, names=["probe"], dest=dest, force=True) == 0
    assert "name: probe" in (dest / "probe" / "SKILL.md").read_text(encoding="utf-8")


def test_dry_run_writes_nothing(tmp_path: Path,
                                capsys: pytest.CaptureFixture[str]) -> None:
    lib = library(tmp_path / "lib", "probe")
    dest = tmp_path / "skills"
    assert call(tmp_path, library_root=lib, names=["probe"], dest=dest, dry_run=True) == 0
    assert not dest.exists()
    assert "would install probe" in capsys.readouterr().out


def test_library_is_found_by_contract_not_by_name(tmp_path: Path) -> None:
    lib = library(tmp_path / "not-the-expected-name", "probe")
    nested = lib / "some" / "deep" / "place"
    nested.mkdir(parents=True)
    assert skill_install.run(args(names=["probe"], dest=tmp_path / "skills"), env={},
                             home=tmp_path / "home", cwd=nested) == 0


def test_list_prints_every_skill_and_writes_nothing(tmp_path: Path,
                                                    capsys: pytest.CaptureFixture[str]) -> None:
    lib = library(tmp_path / "lib", "probe", "second")
    assert call(tmp_path, library_root=lib, list=True) == 0
    printed = capsys.readouterr().out
    assert "probe" in printed and "second" in printed
    assert not (tmp_path / "skills").exists()


def test_an_unknown_skill_is_named(tmp_path: Path) -> None:
    lib = library(tmp_path / "lib", "probe")
    with pytest.raises(SkillSetupError) as raised:
        call(tmp_path, library_root=lib, names=["absent"], dest=tmp_path / "skills")
    assert "absent" in str(raised.value)


def test_skills_dir_env_supplies_the_destination(tmp_path: Path) -> None:
    lib = library(tmp_path / "lib", "probe")
    dest = tmp_path / "from-env"
    code = skill_install.run(args(names=["probe"]), env={"SKILLS_DIR": str(dest)},
                             home=tmp_path / "home", cwd=lib)
    assert code == 0
    assert (dest / "probe" / "SKILL.md").is_file()


def test_the_cli_reaches_the_verb(tmp_path: Path,
                                  capsys: pytest.CaptureFixture[str]) -> None:
    """`council setup skill` must go through `main`, not fall through to `review`.

    The module tests above call `run` directly, so they cannot see a missing dispatch
    branch: the verb parsed, the parser accepted it, and `main` still asked for a review.
    """
    from council import cli

    lib = library(tmp_path / "lib", "probe")
    assert cli.main(["setup", "skill", "--library", str(lib), "--list"]) == 0
    assert "probe" in capsys.readouterr().out

    dest = tmp_path / "skills"
    assert cli.main(["setup", "skill", "probe", "--library", str(lib),
                     "--dest", str(dest)]) == 0
    assert (dest / "probe" / "SKILL.md").is_file()


def test_a_cli_refusal_exits_three(tmp_path: Path,
                                   capsys: pytest.CaptureFixture[str]) -> None:
    """A refusal is exit 3, like every other error the CLI reports."""
    from council import cli
    from council.cli_parser import EXIT_ERROR

    lib = library(tmp_path / "lib", "probe")
    assert cli.main(["setup", "skill", "absent", "--library", str(lib),
                     "--dest", str(tmp_path / "skills")]) == EXIT_ERROR
    assert "absent" in capsys.readouterr().err


def test_agent_with_no_installed_directory_is_refused(tmp_path: Path) -> None:
    lib = library(tmp_path / "lib", "probe")
    with pytest.raises(SkillSetupError) as raised:
        skill_install.run(args(names=["probe"], agent="claude"), env={},
                          home=tmp_path / "home", cwd=lib)
    assert "--dest" in str(raised.value)
