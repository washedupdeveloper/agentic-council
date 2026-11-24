"""Run an OpenSpec change task by task, stopping before irreversible actions.

The runner is the owner's proxy for the repetitive part: it writes a prompt,
runs the selected profile, requires `collab/<task>.md`, runs the task predicate,
and ticks the checkbox only after the predicate passes. It may read, run tests
and write workspace files. It never commits, pushes or changes a profile; a
PATH shim refuses those commands to the worker as well.
"""

from __future__ import annotations

import argparse
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

CHECKBOX = re.compile(r"^(\s*-\s*\[)([ xX])(\]\s*)(\d+(?:\.\d+)+)(\s+)(.*)$")
TASK_IN_PROMPT = re.compile(r"task `([^`]+)`")
TASK_KEY = re.compile(r'^  (?:\"([^\"]+)\"|([^\s:#][^:]*)):\s*$')
FIELD = re.compile(r"^    ([a-z_]+):\s*(.*)$")
ITEM = re.compile(r"^ {4,}-\s*(.*)$")


class MilestoneError(RuntimeError):
    """The run cannot continue without guessing."""


@dataclass(frozen=True, slots=True)
class Task:
    identifier: str
    title: str
    done: bool
    line: str


def read_tasks(path: Path) -> list[Task]:
    tasks: list[Task] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        match = CHECKBOX.match(line)
        if match:
            title = re.sub(r"\s*\[(?:type|verify|profile):[^\]]*\]", "", match.group(6)).strip()
            tasks.append(Task(match.group(4), title, match.group(2).lower() == "x", line))
    return tasks


#: The escapes YAML defines inside a double-quoted scalar. Anything else after
#: a backslash is kept as written: a predicate is shell text, and a stray
#: backslash is likelier to be a literal than a typo.
_YAML_ESCAPES = {
    "0": "\0", "a": "\a", "b": "\b", "t": "\t", "n": "\n", "v": "\v",
    "f": "\f", "r": "\r", "e": "\x1b", " ": " ", '"': '"', "/": "/",
    "\\": "\\", "N": "\x85", "_": "\xa0", "L": "\u2028", "P": "\u2029",
}


def _yaml_escape(body: str, index: int) -> tuple[str, int] | None:
    """One escape at `body[index]`, or None when the backslash is literal."""
    if index + 1 >= len(body):
        return None
    marker = body[index + 1]
    if marker in _YAML_ESCAPES:
        return _YAML_ESCAPES[marker], index + 2
    if marker in ("x", "u", "U"):
        width = {"x": 2, "u": 4, "U": 8}[marker]
        digits = body[index + 2:index + 2 + width]
        if len(digits) == width:
            try:
                return chr(int(digits, 16)), index + 2 + width
            except ValueError:
                return None
    return None


def _inline_list(value: str) -> list[str]:
    """Read a YAML-ish inline list without dropping an unquoted neighbour.

    A quoted item keeps its own quoting: a predicate such as
    `test -f 'release notes'` must reach the shell with the quote intact, or the
    filename becomes two arguments. Inside a double-quoted item the YAML escapes
    are decoded, because `\u0020` and `\t` change the command the shell runs;
    inside a single-quoted item a doubled apostrophe is a literal apostrophe.
    """
    value = value.strip()
    if not value.startswith("["):
        return [value.strip("\"'")] if value else []
    body = value[1:-1].strip()
    if not body:
        return []
    items: list[str] = []
    token: list[str] = []
    quote: str | None = None
    #: Whether the last character came from inside a quote, or was a visible
    #: character outside one. Trailing whitespace is only insignificant when it
    #: was written outside every quote.
    protected = False
    #: Whether the token is a finished quoted item. It is then taken literally:
    #: no trailing whitespace outside the quote can revise it.
    closed = False
    index = 0
    while index < len(body):
        char = body[index]
        if quote == '"' and char == "\\":
            decoded = _yaml_escape(body, index)
            if decoded is not None:
                text, index = decoded
                token.append(text)
                protected = True
                continue
            token.append(char)
            protected = True
        elif quote is not None:
            if char == quote:
                if char == "'" and body[index + 1:index + 2] == "'":
                    token.append("'")
                    index += 2
                    protected = True
                    continue
                quote = None
                # The item is complete as written. Whitespace before the comma
                # is syntax; drop it without touching what the quote held.
                closed = True
            else:
                token.append(char)
                protected = True
        elif char.isspace() and (closed or not token):
            # Whitespace outside a finished quote, or before the item starts, is
            # syntax: skip it. `closed` survives, so a quoted predicate is taken
            # literally even with a space after its closing quote.
            index += 1
            continue
        elif char in ("'", '"') and not token:
            quote = char
        elif char == ",":
            item = _item(token, protected or closed)
            if item:
                items.append(item)
            token = []
            protected = False
            closed = False
        else:
            token.append(char)
            protected = not char.isspace()
        index += 1
    item = _item(token, protected or closed)
    if item:
        items.append(item)
    return items


def _item(token: list[str], protected: bool) -> str:
    """One item, keeping whitespace that was written inside a quote."""
    text = "".join(token)
    return text if protected else text.strip()


def _strip_comment(line: str) -> str:
    """Remove a YAML comment only when the hash is outside a quoted value."""
    quote: str | None = None
    index = 0
    while index < len(line):
        char = line[index]
        if quote is not None and quote == '"' and char == "\\":
            index += 2
            continue
        if quote is not None:
            if char == quote:
                quote = None
        elif char in ("'", '"'):
            quote = char
        elif char == "#" and (index == 0 or line[index - 1].isspace()):
            return line[:index]
        index += 1
    return line


def load_routing(change: Path) -> dict[str, dict[str, Any]]:
    path = change / "routing.yaml"
    if not path.is_file():
        raise MilestoneError(
            f"no routing.yaml in {change}; run `surplus-select draft --change {change}` first"
        )
    tasks: dict[str, dict[str, Any]] = {}
    current: dict[str, Any] | None = None
    collecting = False
    in_tasks = False
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = _strip_comment(raw).rstrip()
        if not line.strip() or line.strip() == "---":
            continue
        if line.strip() == "tasks:":
            in_tasks = True
            current = None
            continue
        if not in_tasks:
            continue
        if not line.startswith(" "):
            break
        key = TASK_KEY.match(line)
        if key:
            identifier = (key.group(1) or key.group(2) or "").strip()
            if identifier:
                current = {}
                tasks[identifier] = current
                collecting = False
            continue
        field = FIELD.match(line)
        if field is not None and current is not None:
            name, value = field.group(1), field.group(2).strip()
            if name == "verify":
                current["verify"] = _inline_list(value)
                collecting = not value
            else:
                current[name] = value.strip("\"'")
                collecting = False
            continue
        item = ITEM.match(line)
        if item is not None and current is not None and collecting:
            value = item.group(1).strip().strip("\"'")
            if value:
                current.setdefault("verify", []).append(value)
    return tasks


def profile_config(home: Path, profile: str) -> Path:
    if profile in ("", "default"):
        return home / "config.yaml"
    return home / "profiles" / profile / "config.yaml"


def render_prompt(change: Path, task: Task, verify: tuple[str, ...]) -> str:
    template_path = Path(__file__).with_name("milestone-task.txt")
    if not template_path.is_file():
        raise MilestoneError(f"missing prompt template: {template_path}")
    template = template_path.read_text(encoding="utf-8")
    predicates = "\n".join(f"- `{command}`" for command in verify)
    return (
        template.replace("<<change>>", change.name)
        .replace("<<identifier>>", task.identifier)
        .replace("<<title>>", task.title)
        .replace("<<predicates>>", predicates)
    )


def _write_shims(directory: Path, real_git: str, real_hermes: str) -> None:
    git = directory / "git"
    git.write_text(
        "#!/bin/sh\n"
        'for arg in "$@"; do\n'
        '  case "$arg" in\n'
        '    commit|push) echo "milestone: refusing git $arg; approval required" >&2; exit 2;;\n'
        "  esac\n"
        "done\n"
        f"exec {shlex.quote(real_git)} \"$@\"\n",
        encoding="utf-8",
    )
    git.chmod(0o755)
    hermes = directory / "hermes"
    hermes.write_text(
        "#!/bin/sh\n"
        'if [ "$1" = "profile" ]; then\n'
        '  echo "milestone: refusing hermes profile; approval required" >&2\n'
        "  exit 2\n"
        "fi\n"
        f"exec {shlex.quote(real_hermes)} \"$@\"\n",
        encoding="utf-8",
    )
    hermes.chmod(0o755)
    if os.name == "nt":
        (directory / "git.cmd").write_text(
            "@echo off\r\n"
            "for %%A in (%*) do (\r\n"
            '  if /I "%%A"=="commit" goto refuse\r\n'
            '  if /I "%%A"=="push" goto refuse\r\n'
            ")\r\n"
            f'"{real_git}" %*\r\n'
            "exit /b %errorlevel%\r\n"
            ":refuse\r\n"
            "echo milestone: refusing git %*; approval required 1>&2\r\n"
            "exit /b 2\r\n",
            encoding="utf-8",
            newline="",
        )
        (directory / "hermes.cmd").write_text(
            "@echo off\r\n"
            'if /I "%1"=="profile" (\r\n'
            "  echo milestone: refusing hermes profile; approval required 1>&2\r\n"
            "  exit /b 2\r\n"
            ")\r\n"
            f'"{real_hermes}" %*\r\n',
            encoding="utf-8",
            newline="",
        )


#: The interpreter a task predicate runs under. Not the caller's login shell:
#: fish would reject `test -f x` chains and `$?`, and a login profile would make
#: the predicate depend on whoever invoked the runner.
PREDICATE_SHELL = None if os.name == "nt" else "/bin/sh"


def _run(command: str, repo: Path, env: dict[str, str], timeout: int) -> tuple[int, str]:
    result = subprocess.run(
        command, shell=True, executable=PREDICATE_SHELL, cwd=repo, env=env,
        capture_output=True, text=True, timeout=timeout,
    )
    output = (result.stdout or "") + (result.stderr or "")
    return result.returncode, output.strip()


def tick(tasks_path: Path, identifier: str) -> None:
    text = tasks_path.read_text(encoding="utf-8")
    pattern = re.compile(
        rf"^(\s*-\s*\[)([ xX])(\]\s*{re.escape(identifier)}(?:\s|$).*)$", re.MULTILINE
    )
    updated, count = pattern.subn(lambda match: f"{match.group(1)}x{match.group(3)}", text)
    if count != 1:
        raise MilestoneError(f"cannot find exactly one checkbox for task {identifier}")
    tasks_path.write_text(updated, encoding="utf-8")


def _select(tasks: list[Task], args: argparse.Namespace) -> list[Task]:
    selected = [task for task in tasks if not task.done]
    if args.task:
        selected = [task for task in selected if task.identifier == args.task]
    if args.limit:
        selected = selected[: args.limit]
    return selected


def _preflight(change: Path, selected: list[Task], routing: dict[str, dict[str, Any]],
               home: Path, profile: str) -> None:
    if not selected:
        print("nothing to run: every selected task is already ticked")
        return
    missing = []
    for task in selected:
        entry = routing.get(task.identifier)
        if entry is None or not entry.get("verify"):
            missing.append(f"{task.identifier}: no acceptance predicate in routing.yaml")
    if missing:
        raise MilestoneError("\n".join(missing))
    profiles = {
        str(routing[task.identifier].get("profile") or profile) for task in selected
    }
    for name in sorted(profiles):
        config = profile_config(home, name)
        if not config.is_file():
            raise MilestoneError(
                f"profile {name!r} has no config at {config}; run "
                f"`hermes profile create {name} --no-skills --no-alias --description \"council {name} profile\"`"
            )


def _command(args: argparse.Namespace, prompt: Path, profile: str) -> list[str]:
    return [
        args.hermes,
        "-p",
        profile,
        "chat",
        "--query-file",
        str(prompt),
        "--oneshot",
        "-Q",
        "--in",
        str(Path(args.repo).resolve()),
        "--max-turns",
        str(args.max_turns),
    ] + ([] if args.strict_approvals else ["--yolo"])


def run(args: argparse.Namespace) -> int:
    change = Path(args.change).expanduser().resolve()
    repo = Path(args.repo).expanduser().resolve()
    if not change.is_dir():
        raise MilestoneError(f"no change directory at {change}")
    tasks_path = change / "tasks.md"
    tasks = read_tasks(tasks_path)
    routing = load_routing(change)
    selected = _select(tasks, args)
    home = Path(args.hermes_home).expanduser()
    _preflight(change, selected, routing, home, args.profile)
    if not selected:
        return 0
    prompts = change / "collab" / "prompts"
    prompts.mkdir(parents=True, exist_ok=True)
    (change / "collab").mkdir(parents=True, exist_ok=True)
    real_git = shutil.which("git")
    if real_git is None:
        raise MilestoneError("git is not on PATH")
    with tempfile.TemporaryDirectory(prefix="milestone-shim-") as raw:
        shim = Path(raw)
        _write_shims(shim, real_git, str(Path(args.hermes).resolve()))
        base_env = dict(os.environ)
        env = dict(base_env)
        env["PATH"] = str(shim) + os.pathsep + env.get("PATH", "")
        for task in selected:
            entry = routing[task.identifier]
            verify = tuple(str(item) for item in entry["verify"])
            profile = str(entry.get("profile") or args.profile)
            prompt = prompts / f"{task.identifier}.md"
            prompt.write_text(render_prompt(change, task, verify), encoding="utf-8")
            command = _command(args, prompt, profile)
            if args.dry_run:
                print(f"would run: {' '.join(command)}")
                print(f"predicate: {'; '.join(verify)}")
                continue
            print(f"task {task.identifier}: {task.title}")
            result = subprocess.run(command, cwd=repo, env=env, capture_output=True, text=True)
            output = (result.stdout or "") + (result.stderr or "")
            if output.strip():
                print(output.strip())
            if result.returncode != 0:
                print(f"task {task.identifier} stopped: worker exited {result.returncode}")
                return 1
            evidence = change / "collab" / f"{task.identifier}.md"
            if not evidence.is_file() or not evidence.read_text(encoding="utf-8").strip():
                print(f"task {task.identifier} stopped: {evidence} is missing or empty")
                return 1
            for predicate in verify:
                code, detail = _run(predicate, repo, env, args.predicate_timeout)
                if detail:
                    print(detail)
                if code != 0:
                    print(f"task {task.identifier} stopped: predicate failed ({code}): {predicate}")
                    return 1
            tick(tasks_path, task.identifier)
            print(f"task {task.identifier} passed and ticked; no commit or push performed")
    print("run complete; owner commands:")
    print(f"  git -C {repo} add -A && git -C {repo} commit -m \"milestone: complete {change.name}\"")
    print(f"  git -C {repo} push")
    return 0


def show(args: argparse.Namespace) -> int:
    change = Path(args.change).expanduser().resolve()
    tasks = read_tasks(change / "tasks.md")
    routing = load_routing(change)
    for task in _select(tasks, args):
        entry = routing.get(task.identifier, {})
        verify = entry.get("verify") or []
        evidence = change / "collab" / f"{task.identifier}.md"
        print(f"{task.identifier}  {task.title}")
        print(f"  profile: {entry.get('profile') or args.profile}")
        print(f"  predicate: {'; '.join(str(item) for item in verify) or 'MISSING'}")
        print(f"  evidence: {'present' if evidence.is_file() else 'missing'}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="milestone", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name, handler in (("plan", show), ("status", show), ("run", run)):
        item = sub.add_parser(name)
        item.add_argument("--change", required=True)
        item.add_argument("--repo", default=".")
        item.add_argument("--profile", default="council-generalist")
        item.add_argument("--hermes", default=shutil.which("hermes") or "hermes")
        item.add_argument("--hermes-home", default=os.environ.get("HERMES_HOME", str(Path.home() / ".hermes")))
        item.add_argument("--max-turns", type=int, default=30)
        item.add_argument("--predicate-timeout", type=int, default=600)
        item.add_argument("--task", default=None)
        item.add_argument("--limit", type=int, default=0)
        item.add_argument("--dry-run", action="store_true")
        item.add_argument(
            "--strict-approvals",
            action="store_true",
            help="omit --yolo; answer Hermes approval prompts in a TTY",
        )
        item.set_defaults(func=handler)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return int(args.func(args))
    except (MilestoneError, OSError, subprocess.SubprocessError) as exc:
        print(f"milestone: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
