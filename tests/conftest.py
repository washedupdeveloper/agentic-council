"""Shared fixtures for the optional protocol adapters.

The server tests exercise the real `council` command with a deterministic
reviewer. They do not call a model and they do not use the Hermes skill.
"""

from __future__ import annotations

import os
import tomllib
import stat
import subprocess
import sys
from pathlib import Path

import pytest

import council_server

ROOT = Path(__file__).resolve().parent.parent
# Derive the package root from the imported adapter so the mutation harness,
# which runs against a copied `src`, exercises the copied server too.
SOURCE = Path(council_server.__file__).resolve().parent.parent


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True,
                   capture_output=True, text=True,
                   env={**os.environ, "GIT_CONFIG_NOSYSTEM": "1"})


@pytest.fixture()
def review_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "council@example.invalid")
    _git(repo, "config", "user.name", "council test")
    (repo / "README.md").write_text("base\n", encoding="utf-8")
    _git(repo, "add", "README.md")
    _git(repo, "commit", "-q", "-m", "base")
    (repo / "app.py").write_text("# app\npassword = \"secret\"\n", encoding="utf-8")
    _git(repo, "add", "app.py")
    _git(repo, "commit", "-q", "-m", "head")
    return repo


@pytest.fixture()
def fake_reviewer(tmp_path: Path) -> Path:
    script = tmp_path / "fake-reviewer"
    script.write_text(
        f"#!{sys.executable}\n" +
        """import json
import sys

ANSWER = {
    "sections": {
        "security": [{
            "severity": "high",
            "file": "app.py",
            "line": 2,
            "claim": "A password is committed.",
            "proof": {"kind": "present", "params": {
                "path": "app.py", "line": 2, "text": 'password = "secret"'
            }},
        }],
        "correctness": [],
        "readability": [],
        "architecture": [],
        "performance": [],
    }
}

text = json.dumps(ANSWER)
if "--format" in sys.argv:
    print(json.dumps({"type": "text", "text": text}))
    print(json.dumps({"type": "result", "text": text, "exit_code": 0}))
else:
    print(text)
""",
        encoding="utf-8",
    )
    script.chmod(script.stat().st_mode | stat.S_IXUSR)
    return script


@pytest.fixture()
def child_env() -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(SOURCE) + (
        os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else ""
    )
    return env

PERMITS = Path(__file__).with_name("permitted_skips.toml")


def _permitted() -> dict[str, str]:
    if not PERMITS.is_file():
        return {}
    with PERMITS.open("rb") as handle:
        return tomllib.load(handle).get("skip", {})


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    """Fail the gate when a test skipped without the owner's explicit permission.

    A skip exits 0, so a platform guard that quietly disables a test reduces what the
    suite proves without turning anything red. The gate runs with
    ``COUNCIL_STRICT_SKIPS=1``; a skip is accepted only when it names itself in
    ``tests/permitted_skips.toml``. A developer running pytest by hand is unaffected.
    """
    if os.environ.get("COUNCIL_STRICT_SKIPS") != "1":
        return
    reporter = session.config.pluginmanager.getplugin("terminalreporter")
    skipped = list(getattr(reporter, "stats", {}).get("skipped", [])) if reporter else []
    permitted = _permitted()
    unpermitted = [report for report in skipped if report.nodeid not in permitted]
    if not unpermitted:
        return
    print(f"\n{len(unpermitted)} test(s) skipped without permission:")
    for report in unpermitted:
        reason = report.longrepr
        if isinstance(reason, tuple) and len(reason) == 3:
            reason = reason[2]
        print(f"  {report.nodeid}: {reason}")
    print("A test that cannot run is a failure, not a skip. Either make it run, or")
    print("name it in tests/permitted_skips.toml with the owner's reason.")
    session.exitstatus = 1
