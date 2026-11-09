"""Every text file the repository ships ends with a newline."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASES = ("src", "tests", "tools", "docs", "bin", "skills")
ROOTS = ("*.md", "*.toml", "*.nix", "*.lock")
SKIP = {"__pycache__", ".mypy_cache", ".pytest_cache", ".ruff_cache", ".hypothesis"}


def text_files() -> list[Path]:
    found = [path for base in BASES if (ROOT / base).exists()
             for path in (ROOT / base).rglob("*") if path.is_file()]
    found += [path for pattern in ROOTS for path in ROOT.glob(pattern) if path.is_file()]
    return [path for path in found if not (set(path.parts) & SKIP)]


def test_every_shipped_text_file_ends_with_a_newline() -> None:
    """A file without one shows as `\\ No newline at end of file` in every diff."""
    missing: list[str] = []
    for path in text_files():
        data = path.read_bytes()
        if not data:
            continue
        try:
            data.decode("utf-8")
        except UnicodeDecodeError:
            continue
        if not data.endswith(b"\n"):
            missing.append(str(path.relative_to(ROOT)))
    assert not missing, "no trailing newline: " + ", ".join(missing)
