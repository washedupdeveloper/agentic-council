"""Shared fixtures for the optional protocol adapters.

The server tests exercise the real `council` command with a deterministic
reviewer. They do not call a model and they do not use the Hermes skill.
"""

from __future__ import annotations

import os
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

def pytest_sessionfinish(session, exitstatus):  # noqa: ANN001, ARG001 - pytest hook
    """Fail the gate when a test skipped, if the caller asked for proof.

    A skip exits 0, so a platform guard that quietly disables a test reduces what the
    suite proves without turning anything red. The gate runs with
    ``COUNCIL_STRICT_SKIPS=1``; a developer running pytest by hand is unaffected.

    The three sandbox proofs are the reason this exists: they assert that bwrap actually
    isolates a proof, and if user namespaces are unavailable they skip -- leaving green
    over a sandbox nobody demonstrated.
    """
    if os.environ.get("COUNCIL_STRICT_SKIPS") != "1":
        return
    reporter = session.config.pluginmanager.getplugin("terminalreporter")
    skipped = list(getattr(reporter, "stats", {}).get("skipped", [])) if reporter else []
    if not skipped:
        return
    print(f"\n{len(skipped)} test(s) skipped; a skip is not a pass:")
    for report in skipped:
        reason = report.longrepr
        if isinstance(reason, tuple) and len(reason) == 3:
            reason = reason[2]
        print(f"  {report.nodeid}: {reason}")
    session.exitstatus = 1
