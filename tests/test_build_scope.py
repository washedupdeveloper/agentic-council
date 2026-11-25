"""The scope lists must cover what each check reads, or a check goes quietly blind.

Splitting a check's input is only safe when the input is a *superset* of the files
the command opens. An omitted directory does not fail: the check runs, finds less
and passes. That is worse than a slow gate, so the lists are asserted here.

The bindings compose (`codeScope = [...] ++ toolConfig`), so the parser resolves
composition rather than matching one literal block.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

#: Bindings that hold a list of paths, and may name each other.
SCOPES = ("toolConfig", "codeScope", "testScope", "releaseScope")


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def _binding(flake: str, name: str) -> str:
    match = re.search(rf"^\s*{name}\s*=\s*(.*?);\s*$", flake, re.S | re.M)
    assert match is not None, f"{name} is not bound in flake.nix"
    return match.group(1)


def resolve(name: str, flake: str | None = None, seen: tuple[str, ...] = ()) -> set[str]:
    """Every path a scope names, following `++` composition."""
    assert name not in seen, f"cycle: {name}"
    flake = flake if flake is not None else read("flake.nix")
    body = _binding(flake, name)
    paths = set(re.findall(r'"([^"]+)"', body))
    for identifier in SCOPES:
        if identifier != name and re.search(rf"\b{identifier}\b", body):
            paths |= resolve(identifier, flake, (*seen, name))
    return paths


#: A scope argument is either a bare identifier or a parenthesised expression.
_ARGUMENT = re.compile(
    r'mkCheck\s+"([^"]+)"\s+(\([^)]*\)|[A-Za-z_][A-Za-z0-9_]*)', re.S)


def check_scopes() -> dict[str, set[str]]:
    """check name -> every scope identifier its mkCheck call names.

    The argument may be parenthesised and wrapped across lines, so identifiers are
    extracted from the expression rather than assumed to be a single token.
    """
    flake = read("flake.nix")
    found = _ARGUMENT.findall(flake)
    assert found, "no mkCheck calls found"
    result: dict[str, set[str]] = {}
    for name, argument in found:
        identifiers = {word for word in re.findall(r"[A-Za-z_][A-Za-z0-9_]*", argument)
                       if word in SCOPES}
        result.setdefault(name, set()).update(identifiers)
    return result


def test_the_test_scope_covers_every_tree_the_suite_opens() -> None:
    """Every top-level path the suite opens by literal path is in `testScope`."""
    scope = resolve("testScope")
    opened = {
        "flake.nix",
        "flake.lock",
        ".github",
        "docs",
        "openspec",
        "fixtures",
        "skills",
        "claims.toml",
        "README.md",
        "CHANGELOG.md",
        "AGENTS.md",
        "GLOSSARY.md",
        "bin",
        "tools",
    }
    missing = sorted(opened - scope)
    assert not missing, f"testScope omits {missing}: those tests would read nothing"


def test_the_code_scope_covers_the_package_and_its_tests() -> None:
    assert {"src", "tests"} <= resolve("codeScope")


def test_every_scope_carries_the_tool_configuration() -> None:
    """A scoped copy without its tool config checks with different rules.

    Pyright reported type errors in the build sandbox that it does not report in
    the checkout, because its copy had no `pyrightconfig.json` and it fell back to
    loose defaults. Tool config therefore travels with every scope.
    """
    for name in SCOPES:
        scope = resolve(name)
        assert "pyproject.toml" in scope, f"{name} omits pyproject.toml"
        assert "pyrightconfig.json" in scope, f"{name} omits pyrightconfig.json"


def test_every_scope_path_exists() -> None:
    """A typo in a scope list is an evaluation error, not a silent omission."""
    for name in SCOPES:
        paths = resolve(name)
        assert paths, f"{name} names nothing"
        for path in sorted(paths):
            assert (ROOT / path).exists(), f"{name} names a path that is not there: {path}"


def test_every_check_declares_a_scope() -> None:
    """A check that fell back to the whole tree would invalidate on every edit."""
    scopes = check_scopes()
    assert len(scopes) >= 10, f"only found {sorted(scopes)}: the parser missed calls"
    for name, identifiers in scopes.items():
        assert identifiers, f"{name} declares no scope, so it would rebuild on every edit"


def test_a_check_that_runs_the_suite_carries_the_suite_scope() -> None:
    """A check whose command runs pytest needs everything pytest opens.

    `mutations` and `differential` execute the suite; `server-mcp` and
    `server-acp` only import their module, so `codeScope` is right for them.
    """
    # `claims` runs `council-verify`, which executes every claim: the ones that
    # run pytest need the suite's inputs, so it is a suite check too.
    runs_suite = {"tests", "mutations", "differential", "claims"}
    for name, arg in check_scopes().items():
        if name in runs_suite:
            assert "testScope" in arg, (
                f"{name} runs the suite but its scope is {arg}, not testScope")


def test_the_scope_guard_can_read_the_flake_it_guards() -> None:
    """This module parses flake.nix, so flake.nix must be in the suite's scope.

    In the build sandbox the suite sees only its declared inputs. Without
    `flake.nix` in `testScope`, every test here died with FileNotFoundError --
    which is precisely the failure a scope must not be allowed to hide.
    """
    assert (ROOT / "flake.nix").is_file()
    assert (ROOT / "flake.lock").is_file()
    assert (ROOT / "tests/test_build_scope.py").is_file()
