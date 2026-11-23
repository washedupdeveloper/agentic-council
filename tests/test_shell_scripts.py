"""The shell contract: a script names bash, a predicate runs under /bin/sh.

Fish is the login shell on some NixOS and WSL images. It cannot run a bash
script body and `$?` is a syntax error there, so an invocation routed through
the login shell fails before the command starts. These tests pin the two halves
of the fix: repository scripts declare and parse as bash, and the milestone
runner does not consult the caller's shell.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = sorted(ROOT.glob("tools/*.sh"))
SHELL_DOC = ROOT / "docs" / "SHELLS.md"
BASH_SHEBANGS = {"#!/usr/bin/env bash", "#!/bin/bash"}


def test_the_repository_ships_shell_scripts() -> None:
    """An empty glob would make every check below vacuous."""
    assert SCRIPTS, "no tools/*.sh found"


def test_every_shell_script_declares_bash() -> None:
    missing = [
        path.relative_to(ROOT).as_posix()
        for path in SCRIPTS
        if path.read_text(encoding="utf-8").splitlines()[0].strip() not in BASH_SHEBANGS
    ]
    assert not missing, "script(s) without a bash shebang: " + ", ".join(missing)


def test_every_shell_script_parses_as_bash() -> None:
    """`bash -n` catches syntax a fish-parsed body would silently mangle."""
    failures: list[str] = []
    for path in SCRIPTS:
        result = subprocess.run(
            ["bash", "-n", str(path)], capture_output=True, text=True, timeout=60
        )
        if result.returncode != 0:
            failures.append(f"{path.name}: {result.stderr.strip()}")
    assert not failures, "bash syntax error(s): " + "; ".join(failures)


def test_no_script_binds_itself_to_fish() -> None:
    """A fish shebang or a bare `$status` would make the script fish-only."""
    offenders: list[str] = []
    for path in SCRIPTS:
        text = path.read_text(encoding="utf-8")
        if "#!/usr/bin/env fish" in text or "#!/usr/bin/fish" in text:
            offenders.append(f"{path.name}: fish shebang")
        if "$status" in text:
            offenders.append(f"{path.name}: fish $status")
    assert not offenders, "fish-only construct(s): " + "; ".join(offenders)


def test_the_shell_document_is_indexed() -> None:
    index = (ROOT / "docs" / "README.md").read_text(encoding="utf-8")
    assert "(SHELLS.md)" in index, "docs/SHELLS.md is not linked from the index"


def test_the_shell_document_states_each_invocation() -> None:
    text = SHELL_DOC.read_text(encoding="utf-8")
    for needle in (
        "wsl.exe -d NixOS --exec bash",
        "$status",
        "$LASTEXITCODE",
        "/bin/sh",
        "POSIX shell, not fish and not bash",
        "does **not** start a login shell",
    ):
        assert needle in text, f"docs/SHELLS.md does not mention {needle!r}"
