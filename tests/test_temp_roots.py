"""Every pytest this repository launches gets its own basetemp.

pytest only builds and prunes `TMPDIR/pytest-of-<user>/pytest-N` when no basetemp is
given, and that cleanup leaves an unclosed scandir handle -- which warns from its own
finaliser and, under `filterwarnings = ["error"]`, fails whichever test is running.
Measured: one claim in six rounds at four workers. A given basetemp skips the path.

This holds the callers to it, so the fix does not depend on anyone remembering.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

from council import claims

ROOT = Path(__file__).resolve().parent.parent


def load_tool():
    spec = importlib.util.spec_from_file_location(
        "mutation_check", ROOT / "tools" / "mutation_check.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _capture(monkeypatch, module) -> dict[str, object]:
    seen: dict[str, object] = {}

    def fake_run(argv, **kwargs):
        seen["argv"] = list(argv)
        seen["env"] = dict(kwargs.get("env") or {})
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(module.subprocess, "run", fake_run)
    return seen


def _basetemp(argv: list[str]) -> str | None:
    for token in argv:
        if token.startswith("--basetemp="):
            return token.split("=", 1)[1]
    return None


def test_a_claim_runs_pytest_under_its_own_basetemp(monkeypatch, tmp_path: Path) -> None:
    seen = _capture(monkeypatch, claims)
    claim = claims.Claim(id="x", text="y", check="python3 -m pytest tests/test_files.py -q")

    claims.run_one(claim, tmp_path)

    argv = seen["argv"]
    assert isinstance(argv, list)
    base = _basetemp(argv)
    assert base is not None, argv
    env = seen["env"]
    assert isinstance(env, dict)
    assert Path(base).is_relative_to(Path(env["TMPDIR"]))


def test_a_claim_that_is_not_pytest_is_left_alone(monkeypatch, tmp_path: Path) -> None:
    """The flag only goes to pytest; another command must not be edited."""
    seen = _capture(monkeypatch, claims)
    claim = claims.Claim(id="x", text="y", check="bash ./bin/council-verify")

    claims.run_one(claim, tmp_path)

    argv = seen["argv"]
    assert isinstance(argv, list)
    assert _basetemp(argv) is None


def test_a_mutant_runs_the_suite_under_its_own_basetemp(monkeypatch, tmp_path: Path) -> None:
    module = load_tool()
    seen = _capture(monkeypatch, module)

    module.run_suite(tmp_path)

    argv = seen["argv"]
    assert isinstance(argv, list)
    base = _basetemp(argv)
    assert base is not None, argv
    env = seen["env"]
    assert isinstance(env, dict)
    assert Path(base).is_relative_to(Path(env["TMPDIR"]))
