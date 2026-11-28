"""A subset may prove a catch; only the whole suite may prove a miss.

The fast path is the campaign's only cost reduction that does not narrow what is proven,
and this file is the proof of that sentence: a failing falsifier decides the mutant, a
passing one always falls back, and `--no-fast` runs the suite exactly as before.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load_tool():
    spec = importlib.util.spec_from_file_location(
        "mutation_check_fastpath", ROOT / "tools" / "mutation_check.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_a_failing_falsifier_decides_the_mutant(monkeypatch) -> None:
    module = load_tool()
    seen: list[list[str] | None] = []

    def fake_suite(_src, nodes=None, failfast=False):
        seen.append(nodes)
        if nodes:
            return 1, {"tests/test_a.py::test_a"}
        raise AssertionError("the full suite must not run when the falsifier fails")

    monkeypatch.setattr(module, "run_suite", fake_suite)
    node = "tests/test_a.py::test_a"
    name, caught, hit, problem, by_falsifier = module._score(
        module.MUTATIONS[0], {node: ["claim-one"]}, [node])

    assert caught is True
    assert by_falsifier is True
    assert hit == {"claim-one"}
    assert problem is None
    assert seen == [[node]], "only the falsifier nodes may run"


def test_a_passing_falsifier_falls_back_to_the_whole_suite(monkeypatch) -> None:
    module = load_tool()
    seen: list[list[str] | None] = []

    def fake_suite(_src, nodes=None, failfast=False):
        seen.append(nodes)
        if nodes:
            return 0, set()
        return 1, {"tests/test_b.py::test_b"}

    monkeypatch.setattr(module, "run_suite", fake_suite)
    node = "tests/test_a.py::test_a"
    name, caught, hit, problem, by_falsifier = module._score(
        module.MUTATIONS[0], {"tests/test_b.py::test_b": ["claim-two"]}, [node])

    assert caught is True, "the full suite caught it"
    assert by_falsifier is False, "the catch came from the whole suite, not the subset"
    assert hit == {"claim-two"}
    assert seen == [[node], None], "the subset runs first, then the whole suite"


def test_a_mutant_nothing_catches_is_reported_as_surviving(monkeypatch) -> None:
    module = load_tool()
    monkeypatch.setattr(module, "run_suite", lambda _src, nodes=None, failfast=False: (0, set()))
    node = "tests/test_a.py::test_a"
    _, caught, hit, problem, by_falsifier = module._score(
        module.MUTATIONS[0], {}, [node])
    assert caught is False
    assert hit == set()
    assert problem is None
    assert by_falsifier is False


def test_no_fast_never_runs_a_subset(monkeypatch) -> None:
    module = load_tool()
    seen: list[list[str] | None] = []

    def fake_suite(_src, nodes=None, failfast=False):
        seen.append(nodes)
        return 1, {"tests/test_a.py::test_a"}

    monkeypatch.setattr(module, "run_suite", fake_suite)
    node = "tests/test_a.py::test_a"
    _, caught, _, _, by_falsifier = module._score(
        module.MUTATIONS[0], {node: ["claim-one"]}, [node], fast=False)

    assert caught is True
    assert by_falsifier is False
    assert seen == [None], "--no-fast must run the whole suite"


def test_the_summary_names_both_paths(capsys, monkeypatch) -> None:
    """A silent shift to full-suite scoring is a silent regression; the line makes it visible."""
    module = load_tool()

    def fake_suite(_src, nodes=None, failfast=False):
        # The baseline (no nodes) must be green or nothing is scored at all.
        return (1, {"tests/test_a.py::test_a"}) if nodes else (0, set())

    monkeypatch.setattr(module, "run_suite", fake_suite)
    module.main(["--no-cache", "--jobs", "2", "--only", module.MUTATIONS[0].name])
    output = capsys.readouterr().out
    assert "decided by the declared falsifier" in output
