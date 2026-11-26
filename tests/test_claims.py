"""The registry itself is a claim: it must reject a claim it cannot check.

A registry that silently accepts an entry with no `check` is the same failure it
exists to prevent, one level up — so malformed registries are tested as
carefully as failing checks.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from council.claims import Claim, RegistryError, load, main, render, run_all, run_one

VALID = """
[[claim]]
id = "one"
text = "The first claim holds."
check = "true"

[[claim]]
id = "two"
text = "The second claim holds."
check = "true"
"""


def write(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "claims.toml"
    path.write_text(body, encoding="utf-8")
    return path


def test_a_valid_registry_loads(tmp_path: Path) -> None:
    claims = load(write(tmp_path, VALID))
    assert [c.id for c in claims] == ["one", "two"]
    assert claims[0].check == "true"


def test_a_claim_without_a_check_is_rejected(tmp_path: Path) -> None:
    body = '[[claim]]\nid = "x"\ntext = "No check."\n'
    with pytest.raises(RegistryError, match="check"):
        load(write(tmp_path, body))


def test_a_duplicate_id_is_rejected(tmp_path: Path) -> None:
    body = VALID + '\n[[claim]]\nid = "one"\ntext = "Again."\ncheck = "true"\n'
    with pytest.raises(RegistryError, match="duplicate"):
        load(write(tmp_path, body))


def test_a_text_without_a_period_is_rejected(tmp_path: Path) -> None:
    body = '[[claim]]\nid = "x"\ntext = "not a sentence"\ncheck = "true"\n'
    with pytest.raises(RegistryError, match="period"):
        load(write(tmp_path, body))


def test_an_empty_registry_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(RegistryError, match="no \\[\\[claim\\]\\]"):
        load(write(tmp_path, ""))


def test_a_passing_check_reports_ok(tmp_path: Path) -> None:
    result = run_one(Claim("x", "It holds.", "true"), tmp_path)
    assert result.ok
    assert result.detail == ""


def test_a_failing_check_reports_the_exit_code(tmp_path: Path) -> None:
    result = run_one(Claim("x", "It does not.", "false"), tmp_path)
    assert not result.ok
    assert "exit 1" in result.detail


def test_a_missing_command_is_a_failure_not_a_crash(tmp_path: Path) -> None:
    result = run_one(Claim("x", "It cannot run.", "definitely-not-a-command-xyz"), tmp_path)
    assert not result.ok
    assert "not found" in result.detail


def test_a_timeout_is_a_failure(tmp_path: Path) -> None:
    result = run_one(Claim("x", "It hangs.", "sleep 5"), tmp_path, timeout=1)
    assert not result.ok
    assert "timed out" in result.detail


def test_a_missing_registry_is_a_start_failure(tmp_path: Path) -> None:
    """3 means could not start; 2 stays reserved for an incomplete review."""
    assert main(["--registry", str(tmp_path / "nope.toml")]) == 3


def test_a_missing_flag_value_is_a_start_failure() -> None:
    with pytest.raises(SystemExit) as raised:
        main(["--registry"])
    assert raised.value.code == 3


def test_the_document_is_generated_from_the_registry(tmp_path: Path) -> None:
    """The page cannot list a claim the registry does not have, or miss one it does."""
    registry = write(tmp_path, VALID)
    document = tmp_path / "CLAIMS.md"

    assert main(["--registry", str(registry), "--write", str(document)]) == 0
    assert "| `one` | The first claim holds. | `true` |" in document.read_text(encoding="utf-8")
    assert main(["--registry", str(registry), "--check", str(document)]) == 0

    document.write_text(document.read_text(encoding="utf-8") + "a claim nobody checks\n",
                        encoding="utf-8")
    assert main(["--registry", str(registry), "--check", str(document)]) == 1


def test_render_is_one_row_per_claim(tmp_path: Path) -> None:
    text = render(load(write(tmp_path, VALID)))
    assert text.count("\n| `") == 2


def test_run_all_keeps_going_after_a_failure(tmp_path: Path) -> None:
    claims = [Claim("a", "Fails.", "false"), Claim("b", "Passes.", "true")]
    results = run_all(claims, tmp_path)
    assert [r.ok for r in results] == [False, True]


def test_a_skipped_check_is_not_a_holding_claim(tmp_path: Path) -> None:
    """pytest exits 0 for a skipped node: the command passed without running.

    A claim is a sentence plus the command that would falsify it. A skip falsifies
    nothing, so counting it as a pass would let the registry report proof it never had.
    """
    (tmp_path / "test_probe.py").write_text(
        "import pytest\n\n\n"
        "@pytest.mark.skip(reason='probe')\n"
        "def test_never_runs() -> None:\n"
        "    raise AssertionError('the body must not run')\n",
        encoding="utf-8",
    )
    result = run_one(
        Claim("x", "It holds.", "python3 -m pytest test_probe.py::test_never_runs -q"),
        tmp_path,
    )
    assert not result.ok
    assert "not proven" in result.detail
    assert "probe" in result.detail
