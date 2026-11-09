"""Context: the functions around the change, and the calls they make."""

from __future__ import annotations

from typing import Callable

from council.context import build


def reader(files: dict[str, str]) -> Callable[[str], str | None]:
    return lambda path: files.get(path)


def hunk(*lines: str) -> str:
    return "\n".join(lines)


A = """def helper():
    return 1


def target():
    x = 1
    return x
"""


def test_the_enclosing_function_is_included() -> None:
    diff = ("diff --git a/pkg/a.py b/pkg/a.py\n--- a/pkg/a.py\n+++ b/pkg/a.py\n"
            "@@ -4,3 +4,4 @@\n def target():\n+    x = 1\n     return x\n")
    context = build(diff, reader({"pkg/a.py": A}), ["pkg/a.py"])
    assert [span.name for span in context.spans] == ["target"]
    assert context.spans[0].reason == "enclosing"
    assert "def target():" in context.text


def test_two_changed_functions_are_both_included() -> None:
    source = "def one():\n    return 1\n\n\ndef two():\n    return 2\n"
    diff = ("diff --git a/f.py b/f.py\n--- a/f.py\n+++ b/f.py\n"
            "@@ -1,2 +1,3 @@\n def one():\n+    x = 0\n     return 1\n"
            "@@ -5,2 +5,3 @@\n def two():\n+    y = 0\n     return 2\n")
    context = build(diff, reader({"f.py": source}), ["f.py"])
    assert [span.name for span in context.spans] == ["one", "two"]


def test_no_context_is_the_diff_alone() -> None:
    diff = ("diff --git a/pkg/a.py b/pkg/a.py\n--- a/pkg/a.py\n+++ b/pkg/a.py\n"
            "@@ -4,3 +4,4 @@\n def target():\n+    x = 1\n     return x\n")
    context = build(diff, reader({"pkg/a.py": A}), ["pkg/a.py"], max_depth=-1)
    assert context.spans == ()
    assert context.text == "_(context disabled by the caller)_"


def test_the_enclosing_function_alone_excludes_its_calls() -> None:
    source = ("def helper():\n    return 1\n\n\n"
              "def target():\n    return helper()\n")
    diff = ("diff --git a/f.py b/f.py\n--- a/f.py\n+++ b/f.py\n"
            "@@ -5,2 +5,3 @@\n def target():\n+    x = 0\n     return helper()\n")
    context = build(diff, reader({"f.py": source}), ["f.py"], max_depth=0)
    assert [span.name for span in context.spans] == ["target"]
    assert context.spans[0].depth == 0


def test_the_call_chain_is_followed_two_deep_and_then_stops() -> None:
    source = (
        "def too_deep():\n    return 0\n\n\n"
        "def deep():\n    return too_deep()\n\n\n"
        "def helper():\n    return deep()\n\n\n"
        "def target():\n    value = helper()\n    return helper()\n"
    )
    diff = ("diff --git a/f.py b/f.py\n--- a/f.py\n+++ b/f.py\n"
            "@@ -13,3 +13,4 @@\n def target():\n+    value = helper()\n     return helper()\n")
    context = build(diff, reader({"f.py": source}), ["f.py"])
    assert [span.name for span in context.spans] == ["target", "helper", "deep"]
    assert context.spans[1].depth == 1
    assert context.spans[2].depth == 2


def test_a_call_into_another_module_is_resolved() -> None:
    a = "from .b import calc\n\n\ndef target():\n    return calc()\n"
    b = "def calc():\n    return 1\n"
    diff = ("diff --git a/pkg/a.py b/pkg/a.py\n--- a/pkg/a.py\n+++ b/pkg/a.py\n"
            "@@ -4,2 +4,2 @@\n def target():\n-    return 0\n+    return calc()\n")
    context = build(diff, reader({"pkg/a.py": a, "pkg/b.py": b}), ["pkg/a.py", "pkg/b.py"])
    assert [span.name for span in context.spans] == ["target", "calc"]
    assert context.spans[1].file == "pkg/b.py"


def test_an_attribute_call_on_a_local_module_is_resolved() -> None:
    a = "from . import b\n\n\ndef target():\n    return b.calc()\n"
    b = "def calc():\n    return 1\n"
    diff = ("diff --git a/pkg/a.py b/pkg/a.py\n--- a/pkg/a.py\n+++ b/pkg/a.py\n"
            "@@ -4,2 +4,2 @@\n def target():\n-    return 0\n+    return b.calc()\n")
    context = build(diff, reader({"pkg/a.py": a, "pkg/b.py": b}), ["pkg/a.py", "pkg/b.py"])
    assert [span.name for span in context.spans] == ["target", "calc"]


def test_an_unresolved_call_is_named_not_hidden() -> None:
    a = "from . import missing\n\n\ndef target():\n    return missing.f()\n"
    diff = ("diff --git a/pkg/a.py b/pkg/a.py\n--- a/pkg/a.py\n+++ b/pkg/a.py\n"
            "@@ -4,2 +4,2 @@\n def target():\n-    return 0\n+    return missing.f()\n")
    context = build(diff, reader({"pkg/a.py": a}), ["pkg/a.py"])
    assert "missing.f" in context.unresolved


def test_a_span_over_the_limit_is_named_not_silently_cut() -> None:
    body = "".join(f"    x{i} = {i}\n" for i in range(500))
    source = f"def huge():\n{body}"
    diff = ("diff --git a/f.py b/f.py\n--- a/f.py\n+++ b/f.py\n"
            "@@ -2,2 +2,3 @@\n     x0 = 0\n+    x1 = 1\n     x2 = 2\n")
    context = build(diff, reader({"f.py": source}), ["f.py"])
    assert context.spans == ()
    assert any("span too large" in item for item in context.unresolved)


def test_a_non_python_file_gets_no_context() -> None:
    diff = ("diff --git a/README.md b/README.md\n--- a/README.md\n+++ b/README.md\n"
            "@@ -1,1 +1,2 @@\n # Title\n+More.\n")
    context = build(diff, reader({"README.md": "# Title\nMore.\n"}), ["README.md"])
    assert context.spans == ()
    assert context.digest == build(diff, reader({"README.md": "# Title\nMore.\n"}),
                                   ["README.md"]).digest
