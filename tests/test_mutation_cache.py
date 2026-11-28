"""A cached verdict is only reused for the same experiment.

The cache exists to make a repeated run cheap, not to make a stale one quiet. These
tests pin both halves: an identical tree scores nothing the second time, and any change
to the things a verdict depends on scores it again.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load_tool():
    spec = importlib.util.spec_from_file_location(
        "mutation_check_cache", ROOT / "tools" / "mutation_check.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def fake_tree(root: Path) -> None:
    (root / "src" / "council").mkdir(parents=True)
    (root / "tests").mkdir()
    (root / "src" / "council" / "a.py").write_text("x = 1\n", encoding="utf-8")
    (root / "tests" / "test_a.py").write_text("def test_a(): pass\n", encoding="utf-8")
    (root / "claims.toml").write_text("", encoding="utf-8")


def digest_of(module, root: Path) -> str:
    module.ROOT = root
    return module.tree_digest()


def test_the_digest_is_stable_for_an_unchanged_tree(tmp_path, monkeypatch) -> None:
    module = load_tool()
    fake_tree(tmp_path)
    monkeypatch.setattr(module, "__file__", str(tmp_path / "tools" / "mutation_check.py"))
    (tmp_path / "tools").mkdir()
    (tmp_path / "tools" / "mutation_check.py").write_text("# tool\n", encoding="utf-8")
    first = digest_of(module, tmp_path)
    assert digest_of(module, tmp_path) == first


def test_a_changed_test_changes_the_digest(tmp_path, monkeypatch) -> None:
    module = load_tool()
    fake_tree(tmp_path)
    monkeypatch.setattr(module, "__file__", str(tmp_path / "tools" / "mutation_check.py"))
    (tmp_path / "tools").mkdir()
    (tmp_path / "tools" / "mutation_check.py").write_text("# tool\n", encoding="utf-8")
    before = digest_of(module, tmp_path)
    (tmp_path / "tests" / "test_a.py").write_text("def test_a(): assert 1\n", encoding="utf-8")
    assert digest_of(module, tmp_path) != before


def test_a_changed_source_changes_the_digest(tmp_path, monkeypatch) -> None:
    module = load_tool()
    fake_tree(tmp_path)
    monkeypatch.setattr(module, "__file__", str(tmp_path / "tools" / "mutation_check.py"))
    (tmp_path / "tools").mkdir()
    (tmp_path / "tools" / "mutation_check.py").write_text("# tool\n", encoding="utf-8")
    before = digest_of(module, tmp_path)
    (tmp_path / "src" / "council" / "a.py").write_text("x = 2\n", encoding="utf-8")
    assert digest_of(module, tmp_path) != before


def test_an_unreadable_cache_is_an_empty_one(tmp_path) -> None:
    module = load_tool()
    assert module.load_cache(tmp_path / "missing.json") == {}
    broken = tmp_path / "broken.json"
    broken.write_text("{not json", encoding="utf-8")
    assert module.load_cache(broken) == {}
    not_a_map = tmp_path / "list.json"
    not_a_map.write_text("[1, 2]", encoding="utf-8")
    assert module.load_cache(not_a_map) == {}


def test_the_cache_round_trips(tmp_path) -> None:
    module = load_tool()
    path = tmp_path / "cache.json"
    module.save_cache(path, {"digest": {"mutant": [True, ["claim"], None]}})
    assert module.load_cache(path) == {"digest": {"mutant": [True, ["claim"], None]}}


def test_a_second_run_against_an_identical_tree_pays_no_suite_run(tmp_path, monkeypatch) -> None:
    """The cache's payoff is the baseline: a byte-identical tree pays none of it.

    Every mutant is answered from the cache, so nothing is left to score and the
    unmutated suite is not run again to re-prove a tree that has not changed.
    """
    module = load_tool()
    calls: list[int] = []

    def fake_suite(_src):
        calls.append(1)
        return 0, set()

    monkeypatch.setattr(module, "run_suite", fake_suite)
    cache = tmp_path / "cache.json"
    module.save_cache(cache, {module.tree_digest():
                              {name: [True, [], None] for name in module.mutation_names()}})

    # The planted entries name no claim, so the campaign reports that as a problem and
    # exits non-zero -- which is not what this test is about. The invariant is the cost.
    module.main(["--cache", str(cache), "--jobs", "1"])
    assert calls == [], "an identical tree must not run the suite again"


def test_a_changed_tree_is_scored_again(tmp_path, monkeypatch) -> None:
    module = load_tool()
    calls: list[int] = []
    digests = iter(["one", "two", "two"])

    monkeypatch.setattr(module, "run_suite",
                        lambda _src: (calls.append(1) or (1, {"tests/test_a.py::test_a"})))
    monkeypatch.setattr(module, "tree_digest", lambda: next(digests))
    cache = tmp_path / "cache.json"

    module.main(["--cache", str(cache), "--jobs", "1"])
    first = len(calls)
    calls.clear()
    module.main(["--cache", str(cache), "--jobs", "1"])
    assert len(calls) == first, "a different digest must score everything again"
