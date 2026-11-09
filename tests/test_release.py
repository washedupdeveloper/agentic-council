"""The release check and the bump: three copies of the version, one truth."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import release  # noqa: E402

CHANGELOG = """# Changelog

## [Unreleased]

### Added

- Something new.

"""


def make(root: Path, *, version: str = "0.1.0", changelog: str = CHANGELOG,
         readme: str = "# council\n") -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "pyproject.toml").write_text(
        f'[project]\nname = "council"\nversion = "{version}"\n', encoding="utf-8")
    (root / "CHANGELOG.md").write_text(changelog, encoding="utf-8")
    (root / "README.md").write_text(readme, encoding="utf-8")
    (root / "docs").mkdir(exist_ok=True)
    return root


def test_the_check_passes_before_the_first_release(tmp_path: Path) -> None:
    assert release.check(make(tmp_path / "repo")) == []


def test_the_newest_release_must_match_the_build_metadata(tmp_path: Path) -> None:
    text = CHANGELOG.replace("## [Unreleased]", "## [1.0.0] — 2026-01-01\n\n## [Unreleased]")
    errors = release.check(make(tmp_path / "repo", version="0.1.0", changelog=text))
    assert any("newest release is 1.0.0" in error for error in errors)


def test_released_versions_must_descend(tmp_path: Path) -> None:
    text = ("# Changelog\n\n## [Unreleased]\n\n"
            "## [1.0.0] — 2026-01-01\n\n## [1.1.0] — 2026-02-01\n")
    errors = release.check(make(tmp_path / "repo", version="1.0.0", changelog=text))
    assert any("is not below the release above it" in error for error in errors)


def test_a_duplicate_version_is_refused(tmp_path: Path) -> None:
    text = ("# Changelog\n\n## [Unreleased]\n\n"
            "## [2.0.0] — 2026-02-01\n\n## [2.0.0] — 2026-01-01\n")
    errors = release.check(make(tmp_path / "repo", version="2.0.0", changelog=text))
    assert any("appears twice" in error for error in errors)


def test_a_release_needs_a_valid_date(tmp_path: Path) -> None:
    text = "# Changelog\n\n## [Unreleased]\n\n## [2.0.0] — 2026-13-40\n"
    errors = release.check(make(tmp_path / "repo", version="2.0.0", changelog=text))
    assert any("invalid date" in error for error in errors)


def test_unreleased_must_be_the_first_section(tmp_path: Path) -> None:
    text = ("# Changelog\n\n## [2.0.0] — 2026-02-01\n\n"
            "## [Unreleased]\n\n### Added\n\n- Later.\n")
    errors = release.check(make(tmp_path / "repo", version="2.0.0", changelog=text))
    assert any("first section must be" in error for error in errors)


def test_a_stale_prose_claim_fails_and_names_the_file(tmp_path: Path) -> None:
    repo = make(tmp_path / "repo", readme="# council\n\nCurrent release v1.0.0\n")
    errors = release.check(repo)
    assert any("README.md: claims v1.0.0" in error for error in errors)


def test_a_tag_must_match_the_build_metadata(tmp_path: Path) -> None:
    errors = release.check(make(tmp_path / "repo"), tag="v9.9.9")
    assert any("tag says 9.9.9" in error for error in errors)


def test_a_stale_wheel_name_fails_the_check(tmp_path: Path) -> None:
    ok = make(tmp_path / "repo",
              readme="# council\n\n`council-0.1.0-py3-none-any.whl`\n")
    assert not any("claims" in error for error in release.check(ok))
    stale = make(tmp_path / "other", version="0.2.0",
                 readme="# council\n\n`council-0.1.0-py3-none-any.whl`\n")
    assert any("claims v0.1.0" in error for error in release.check(stale))


def test_bump_moves_the_entries_and_updates_all_three_copies(
        tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    repo = make(tmp_path / "repo", readme="# council\n\nCurrent release v0.1.0\n")
    changed = release.bump(repo, "2.0.0", "2026-11-09")

    assert (repo / "pyproject.toml").read_text(encoding="utf-8").count('version = "2.0.0"') == 1
    text = (repo / "CHANGELOG.md").read_text(encoding="utf-8")
    assert text.startswith("# Changelog")
    assert "## [Unreleased]\n\n## [2.0.0] — 2026-11-09" in text
    assert "- Something new." in text
    assert "Current release v2.0.0" in (repo / "README.md").read_text(encoding="utf-8")
    assert "git tag -a v2.0.0" in capsys.readouterr().out
    assert {path.name for path in changed} == {"CHANGELOG.md", "pyproject.toml", "README.md"}
    assert release.check(repo) == []


def test_bump_refuses_an_empty_unreleased(tmp_path: Path) -> None:
    text = "# Changelog\n\n## [Unreleased]\n\n## [1.0.0] — 2026-01-01\n"
    repo = make(tmp_path / "repo", version="1.0.0", changelog=text)
    with pytest.raises(ValueError, match="nothing to release"):
        release.bump(repo, "2.0.0", "2026-11-09")


def test_bump_refuses_a_version_that_does_not_increase(tmp_path: Path) -> None:
    repo = make(tmp_path / "repo", version="2.0.0")
    with pytest.raises(ValueError, match="does not increase"):
        release.bump(repo, "2.0.0", "2026-11-09")


def test_a_dry_run_writes_nothing(tmp_path: Path) -> None:
    repo = make(tmp_path / "repo", readme="# council\n\nCurrent release v0.1.0\n")
    before = {path: path.read_text(encoding="utf-8") for path in repo.rglob("*") if path.is_file()}
    assert release.bump(repo, "2.0.0", "2026-11-09", dry_run=True) == []
    after = {path: path.read_text(encoding="utf-8") for path in repo.rglob("*") if path.is_file()}
    assert before == after
