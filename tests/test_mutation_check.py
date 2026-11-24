"""The mutation gate must not score mutations against a red baseline."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load_tool():
    spec = importlib.util.spec_from_file_location(
        "mutation_check", ROOT / "tools" / "mutation_check.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_a_red_baseline_stops_before_any_mutation(monkeypatch, capsys) -> None:
    module = load_tool()
    monkeypatch.setattr(module, "run_suite",
                        lambda _src: (1, {"tests/test_broken.py::test_broken"}))
    assert module.main() == 1
    output = capsys.readouterr().out
    assert "BASELINE RED" in output
    assert "tests/test_broken.py::test_broken" in output
