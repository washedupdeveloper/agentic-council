"""What a diff cannot show: the functions around the change, and the calls they make.

Pure: the caller supplies the diff, the repository's Python files and a reader.
Nothing here opens a file, so the selection and the rendering are testable from
strings alone.

The chain is bounded on purpose — depth, spans and total lines. Everything it
could not resolve is named rather than omitted, so the reviewer knows where its
view of the code stops.
"""

from __future__ import annotations

import ast
import hashlib
from dataclasses import dataclass
from typing import Callable, Sequence

from .changes import change_lines

Reader = Callable[[str], "str | None"]

MAX_DEPTH = 2
MAX_SPAN_LINES = 400
MAX_TOTAL_LINES = 1200


@dataclass(frozen=True, slots=True)
class Span:
    """One function body that the reviewer should see."""

    file: str
    start: int
    end: int
    name: str
    reason: str          # "enclosing" or "callee"
    depth: int

    @property
    def lines(self) -> int:
        return self.end - self.start + 1


@dataclass(frozen=True, slots=True)
class Context:
    spans: tuple[Span, ...]
    unresolved: tuple[str, ...]
    text: str
    digest: str


@dataclass(frozen=True, slots=True)
class _Function:
    name: str
    start: int
    end: int
    node: ast.AST

    @property
    def lines(self) -> int:
        return self.end - self.start + 1


def _functions(tree: ast.Module) -> list[_Function]:
    found: list[_Function] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            end = getattr(node, "end_lineno", None)
            if end is not None:
                found.append(_Function(node.name, node.lineno, end, node))
    return found


def _enclosing(functions: Sequence[_Function], line: int) -> _Function | None:
    """The smallest function whose body contains the line."""
    candidates = [f for f in functions if f.start <= line <= f.end]
    return min(candidates, key=lambda f: f.lines, default=None)


def _imports(tree: ast.Module) -> tuple[dict[str, str], dict[str, tuple[str, str]]]:
    """module aliases, and names imported from a module.

    `import a.b as m`       -> aliases["m"] = "a.b"
    `from . import m`       -> aliases["m"] = ".m"
    `from .m import f`      -> names["f"] = (".m", "f")
    """
    aliases: dict[str, str] = {}
    names: dict[str, tuple[str, str]] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.asname:
                    aliases[alias.asname] = alias.name
        elif isinstance(node, ast.ImportFrom):
            base = "." * node.level + (node.module or "")
            for alias in node.names:
                if node.module is None:
                    aliases[alias.asname or alias.name] = f"{base}{alias.name}"
                else:
                    names[alias.asname or alias.name] = (base, alias.name)
    return aliases, names


def _module_candidates(module: str, current: str, files: Sequence[str]) -> list[str]:
    """Files that could define `module`, best first. Bounded: the file list decides."""
    if module.startswith("."):
        directory = current.rsplit("/", 1)[0] if "/" in current else ""
        stem = module.lstrip(".").replace(".", "/")
        base = f"{directory}/{stem}" if stem else directory
        return [candidate for candidate in (f"{base}.py", f"{base}/__init__.py") if candidate in files]
    path = module.replace(".", "/")
    exact = [candidate for candidate in (f"{path}.py", f"{path}/__init__.py") if candidate in files]
    if exact:
        return exact
    suffix = f"/{path}"
    return [candidate for candidate in files
            if candidate.endswith(f"{suffix}.py") or candidate.endswith(f"{suffix}/__init__.py")]


def _top_level(tree: ast.Module, functions: Sequence[_Function], name: str) -> _Function | None:
    for function in functions:
        if function.name == name and any(node is function.node for node in tree.body):
            return function
    return None


def _parse(path: str, read: Reader,
           cache: dict[str, tuple[list[_Function], ast.Module] | None]
           ) -> tuple[list[_Function], ast.Module] | None:
    if path in cache:
        return cache[path]
    text = read(path)
    if text is None:
        cache[path] = None
        return None
    try:
        tree = ast.parse(text)
    except SyntaxError:
        cache[path] = None
        return None
    entry = (_functions(tree), tree)
    cache[path] = entry
    return entry


def _resolve_call(name: str, module: str | None, current: str, files: Sequence[str],
                  read: Reader, cache: dict[str, tuple[list[_Function], ast.Module] | None]
                  ) -> tuple[str, _Function] | None:
    if module is None:
        return None
    candidates = _module_candidates(module, current, files)
    if not candidates:
        return None
    parsed = _parse(candidates[0], read, cache)
    if parsed is None:
        return None
    functions, tree = parsed
    for function in functions:
        # Top-level only: a method is not reachable by name from another module.
        if function.name == name and isinstance(tree, ast.Module):
            parent_ok = any(node is function.node for node in tree.body)
            if parent_ok:
                return candidates[0], function
    return None


def build(patch: str, read: Reader, files: Sequence[str],
          max_depth: int = MAX_DEPTH) -> Context:
    """Select the spans around the change, then the functions they call.

    `max_depth` is the lever the caller has over the prompt's size: 0 is the
    diff alone, 1 adds the enclosing function, 2 also follows its calls. The
    line and span limits below bound each level; this bounds how many levels
    exist at all.
    """
    if max_depth < 0:
        text = "_(context disabled by the caller)_"
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
        return Context((), (), text, digest)
    changes = change_lines(patch)
    cache: dict[str, tuple[list[_Function], ast.Module] | None] = {}
    spans: list[Span] = []
    unresolved: set[str] = set()
    seen: set[tuple[str, int, int]] = set()
    budget = MAX_TOTAL_LINES

    queue: list[tuple[str, _Function, int, str]] = []
    for path in sorted(changes):
        if not path.endswith(".py"):
            continue
        parsed = _parse(path, read, cache)
        if parsed is None:
            unresolved.add(f"{path} (not parsable)")
            continue
        functions, _tree = parsed
        added, removed = changes[path]
        for line in sorted(added | removed):
            function = _enclosing(functions, line)
            if function is None:
                continue
            key = (path, function.start, function.end)
            if key in seen:
                continue
            seen.add(key)
            queue.append((path, function, 0, "enclosing"))

    while queue and budget > 0:
        path, function, depth, reason = queue.pop(0)
        if function.lines > MAX_SPAN_LINES:
            unresolved.add(f"{path}:{function.start}-{function.end} (span too large)")
            continue
        if function.lines > budget:
            unresolved.add(f"{path}:{function.start}-{function.end} (context budget)")
            continue
        spans.append(Span(path, function.start, function.end, function.name, reason, depth))
        budget -= function.lines
        if depth >= max_depth:
            continue

        parsed = _parse(path, read, cache)
        if parsed is None:
            continue
        _, tree = parsed
        aliases, names = _imports(tree)
        for node in ast.walk(function.node):
            if not isinstance(node, ast.Call):
                continue
            target: tuple[str, _Function] | None = None
            if isinstance(node.func, ast.Name):
                if node.func.id in names:
                    module, symbol = names[node.func.id]
                    target = _resolve_call(symbol, module, path, files, read, cache)
                else:
                    local = _top_level(tree, functions, node.func.id)
                    if local is not None and local is not function:
                        target = (path, local)
            elif isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name):
                alias = aliases.get(node.func.value.id)
                if alias is not None:
                    target = _resolve_call(node.func.attr, alias, path, files, read, cache)
                    if target is None:
                        unresolved.add(f"{node.func.value.id}.{node.func.attr}")
            if target is None:
                continue
            target_file, callee = target
            key = (target_file, callee.start, callee.end)
            if key in seen:
                continue
            seen.add(key)
            queue.append((target_file, callee, depth + 1, "callee"))

    ordered = tuple(sorted(unresolved))
    text = _render(spans, ordered, read)
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
    return Context(tuple(spans), ordered, text, digest)


def _render(spans: Sequence[Span], unresolved: Sequence[str], read: Reader) -> str:
    blocks: list[str] = []
    for span in spans:
        text = read(span.file)
        if text is None:
            continue
        body = "\n".join(text.splitlines()[span.start - 1:span.end])
        heading = "encloses the change" if span.reason == "enclosing" else f"called, depth {span.depth}"
        blocks.append(f"### {span.file}:{span.start}-{span.end} — `{span.name}` ({heading})\n"
                      f"```python\n{body}\n```")
    if unresolved:
        blocks.append("### Not resolved\n" + "\n".join(f"- {name}" for name in unresolved))
    return "\n\n".join(blocks) if blocks else "_(no surrounding function was found)_"