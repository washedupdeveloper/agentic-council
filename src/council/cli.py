"""CLI: 0 pass, 1 fail, 2 incomplete, 3 could not start. `--report` exits 0."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
import unicodedata
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import NoReturn, Sequence

from . import baseline as baseline_io
from . import doctor as diagnostics
from .config import ConfigError
from .domain.baseline import Baseline
from .paths import validate_run_id
from .pr import PullRequest, resolve as resolve_pr, verify_checkout
from .repo import ReviewError, init as init_repo
from .run import (DEFAULT_PROFILE, PROMPT_LIMIT, Plan, PromptTooLarge, Report,
                  ReviewRequest, plan, review)
from .runner import DEFAULT_IDLE_TIMEOUT, hermes_runner
from .sarif import render as render_sarif
from .verdict import Result, Verdict
from .version import current_version

EXIT_ERROR = 3


def _positive(value: str) -> int:
    try:
        number = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("expected a positive number") from exc
    if number < 1:
        raise argparse.ArgumentTypeError("expected at least 1")
    return number


def _samples(value: str) -> int | None:
    """`--samples auto` or a positive count."""
    if value == "auto":
        return None
    try:
        number = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("expected a number or 'auto'") from exc
    if number < 1:
        raise argparse.ArgumentTypeError("expected at least 1")
    return number


def _path(value: str) -> Path:
    if not value.strip():
        raise argparse.ArgumentTypeError("expected a path, not an empty string")
    return Path(value)


def _non_negative(value: str) -> int:
    try:
        number = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("expected a non-negative number") from exc
    if number < 0:
        raise argparse.ArgumentTypeError("expected 0 or more")
    return number


class _Parser(argparse.ArgumentParser):
    """argparse exits 2 on a usage error; 2 already means INCOMPLETE here."""

    def error(self, message: str) -> NoReturn:
        self.print_usage(sys.stderr)
        self.exit(EXIT_ERROR, f"council: {message}\n")


def _safe(text: object) -> str:
    """One printable line: model output must not drive the terminal."""
    return "".join(ch if unicodedata.category(ch) not in {"Cc", "Cf", "Cs", "Zl", "Zp"}
                   else " " for ch in str(text))


def _add_review_arguments(parser: argparse.ArgumentParser, *, advice: bool,
                          base: bool = True) -> None:
    """The review surface, shared by `review` and `ci`.

    `ci` is the gate without the advice switches: it always prints the verdict
    as JSON and always exits with it. A CI entry that could be told to exit 0
    is not a gate.
    """
    parser.add_argument("-C", "--repo", type=_path, default=Path("."),
                        help="repository to review (default: the current directory)")
    if base:
        parser.add_argument("--base", help="revision to diff against (default: origin/HEAD, then HEAD~1)")
    parser.add_argument("--samples", type=_samples, default=None,
                        help="samples: N, or auto (default: 1 clean, 2 to confirm, 3 to break a tie); per unit when sliced")
    parser.add_argument("--profile", default=DEFAULT_PROFILE, help="Hermes profile to ask")
    parser.add_argument("--reviewer", default="hermes",
                        help="binary that answers a sample (default: hermes)")
    parser.add_argument("--sample-timeout", type=_positive, default=900, metavar="SECONDS",
                        help="give up on one sample after N seconds (default: 900)")
    parser.add_argument("--time-budget", type=_non_negative, default=0, metavar="SECONDS",
                        help="stop starting units after N seconds (default: 0, no budget)")
    parser.add_argument("--reasoning", default=None,
                        choices=("none", "minimal", "low", "medium", "high",
                                 "xhigh", "max", "ultra"),
                        help="reasoning effort for this review (default: the profile's setting)")
    parser.add_argument("--stream", action=argparse.BooleanOptionalAction, default=True,
                        help="read the reviewer as JSON events and kill a silent stream (default: on)")
    parser.add_argument("--idle-timeout", type=_positive, default=DEFAULT_IDLE_TIMEOUT,
                        metavar="SECONDS",
                        help="kill a stream with no event for N seconds (default: 120)")
    parser.add_argument("--sandbox", action=argparse.BooleanOptionalAction, default=None,
                        help="run the reviewer in a bwrap sandbox (default: on when bwrap is available)")
    parser.add_argument("--ephemeral", action=argparse.BooleanOptionalAction, default=True,
                        help="keep run state in a temp tree and remove it (default); "
                             "--no-ephemeral writes .council/runs")
    parser.add_argument("--keep", type=_path, default=None, metavar="DIR",
                        help="copy the run directory here before the ephemeral tree is removed")
    parser.add_argument("--prompt", type=_path, default=None,
                        help="reviewer prompt to use instead of the one shipped with council")
    parser.add_argument("--sarif", type=_path, default=None, metavar="PATH",
                        help="also write proven findings as a SARIF 2.1.0 log")
    parser.add_argument("--run-id", default=None,
                        help="name this run instead of using a timestamp (refused if it exists)")
    parser.add_argument("--baseline", type=_path, default=None, metavar="PATH",
                        help="accepted-risk baseline to apply after the evidence verdict")
    parser.add_argument("--baseline-from-base", action="store_true",
                        help="read --baseline from the base revision (default: on for ci/pr)")
    parser.add_argument("--baseline-strict", action="store_true",
                        help="fail when a baseline entry is expired or stale")
    parser.add_argument("--allow-baseline-change", action="store_true",
                        help="allow the reviewed diff to edit the baseline (maintenance only)")
    parser.add_argument("--context-url", action="append", default=[], metavar="URL",
                        help="fetch this URL as reference context (repeatable; never a proof)")
    parser.add_argument("--context-depth", type=int, choices=(0, 1, 2, 3), default=3,
                        help="0 diff only, 1 enclosing function, 2 +one call level, 3 +two (default)")
    parser.add_argument("--max-prompt-bytes", type=_positive, default=PROMPT_LIMIT,
                        metavar="N",
                        help="refuse a prompt larger than N bytes (default: 32768)")
    parser.add_argument("--allow-large-prompt", action="store_true",
                        help="send an oversized prompt without asking (autonomous allow)")
    if advice:
        parser.add_argument("--autonomous", action="store_true",
                            help="never ask: refuse an oversized prompt, exit 3")
        parser.add_argument("--plan", action="store_true",
                            help="show units and prompt sizes; call no reviewer and write no run")
        parser.add_argument("--report", action="store_true",
                            help="advice only: exit 0 whatever the verdict")
        parser.add_argument("--json", action="store_true", help="print the run's verdict.json")


def build_parser() -> argparse.ArgumentParser:
    parser = _Parser(prog="council", description="A review is a claim until a check settles it.")
    parser.add_argument("--version", action="version",
                        version=f"%(prog)s {current_version()}")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("review", help="review a change; exits 0/1/2")
    _add_review_arguments(run, advice=True)

    ci = sub.add_parser("ci", help="the gate for CI: prints verdict.json, exits 0/1/2")
    _add_review_arguments(ci, advice=False)
    ci.set_defaults(report=False, json=True, baseline_from_base=True)

    pr = sub.add_parser("pr", help="review a GitHub pull request by number")
    pr.add_argument("number", type=int, help="pull request number")
    _add_review_arguments(pr, advice=True, base=False)
    pr.set_defaults(baseline_from_base=True)

    baseline = sub.add_parser("baseline", help="create or prune an accepted-risk baseline")
    baseline_sub = baseline.add_subparsers(dest="baseline_action", required=True)
    create = baseline_sub.add_parser("create", help="snapshot proven blocking findings from a run")
    create.add_argument("--from", dest="from_run", type=_path, required=True, metavar="DIR",
                        help="kept run directory containing verdict.json")
    create.add_argument("--out", type=_path, required=True, metavar="PATH")
    create.add_argument("--owner", required=True, help="person or team accepting the risk")
    create.add_argument("--reason", required=True, help="why the accepted risk is tolerated")
    create.add_argument("--days", type=_positive, default=90, metavar="N",
                        help="days until the accepted risk expires (default: 90)")
    prune = baseline_sub.add_parser("prune", help="remove entries no longer found in a run")
    prune.add_argument("--baseline", type=_path, required=True, metavar="PATH")
    prune.add_argument("--from", dest="from_run", type=_path, required=True, metavar="DIR")
    prune.add_argument("--write", action="store_true",
                       help="write the pruned baseline (default: report only)")

    init = sub.add_parser("init", help="add .council/ to the repository's .gitignore")
    init.add_argument("-C", "--repo", type=_path, default=Path("."))

    doctor = sub.add_parser("doctor", help="check that this machine can run a review")
    doctor.add_argument("--profile", default=DEFAULT_PROFILE, help="Hermes profile to ask")
    doctor.add_argument("--reviewer", default="hermes",
                        help="binary that answers a sample (default: hermes)")
    doctor.add_argument("--probe-timeout", type=_positive, default=60, metavar="SECONDS",
                        help="how long the profile has to answer the probe (default: 60)")
    doctor.add_argument("--json", action="store_true", help="print the checks as JSON")
    return parser


_OVERSIZE_HELP = """\
council: why there is a limit
  A prompt above the limit is not sent. A model can sit on a large prompt until
  its timeout and be retried once: that looks like a hang and costs the whole
  wait. Measured with this provider: a 2.8 KB prompt was answered; a 60 KB
  prompt was not. The limit is a starting point, not a rule — raise it for this
  run, or narrow the change with a base revision.
"""


def _oversize_decision(exc: PromptTooLarge, *, allow_base: bool = True) -> tuple[str, int | str | None]:
    """Ask a person what to do. Empty input or EOF cancels: silence is not consent."""
    while True:
        print(f"council: the prompt for this change is {exc.size:,} bytes; "
              f"the limit is {exc.limit:,}.", file=sys.stderr)
        print("council: nothing has been sent to the model. how should this proceed?",
              file=sys.stderr)
        print("  allow           send it anyway\n"
              "  budget N        set the limit to N bytes and retry\n"
              "  base REV        review a narrower change\n"
              "  context N       layers: 0 none, 1 enclosing, 2 +1 call, 3 +2\n"
              "  ?               explain the limit\n"
              "  cancel          stop (exit 3)", file=sys.stderr)
        try:
            line = sys.stdin.readline()
        except (OSError, UnicodeDecodeError):
            return ("cancel", None)
        if not line.strip():
            return ("cancel", None)
        command, _, rest = line.strip().partition(" ")
        rest = rest.strip()
        if command == "allow":
            return ("allow", None)
        if command == "budget":
            try:
                number = int(rest)
            except ValueError:
                print("council: budget needs a number of bytes", file=sys.stderr)
                continue
            if number < 1:
                print("council: budget needs at least 1 byte", file=sys.stderr)
                continue
            return ("budget", number)
        if command == "base":
            if not allow_base:
                print("council: the PR base is fixed by GitHub; choose context, budget or allow",
                      file=sys.stderr)
                continue
            if not rest:
                print("council: base needs a revision", file=sys.stderr)
                continue
            return ("base", rest)
        if command == "context":
            try:
                depth = int(rest)
            except ValueError:
                print("council: context needs 0, 1, 2 or 3", file=sys.stderr)
                continue
            if depth not in (0, 1, 2, 3):
                print("council: context needs 0, 1, 2 or 3", file=sys.stderr)
                continue
            return ("context", depth)
        if command in ("?", "help"):
            print(_OVERSIZE_HELP, file=sys.stderr)
            continue
        if command in ("cancel", "q"):
            return ("cancel", None)
        print(f"council: {command!r} is not one of the choices", file=sys.stderr)


def _request(args: argparse.Namespace, *, allow: bool | None = None) -> ReviewRequest:
    """The request the CLI's parsed arguments describe."""
    return ReviewRequest(
        repo=args.repo, base=args.base, samples=args.samples,
        profile=args.profile, prompt=args.prompt, run_id=args.run_id,
        context_urls=tuple(args.context_url),
        allow_large_prompt=args.allow_large_prompt if allow is None else allow,
        max_prompt_bytes=args.max_prompt_bytes,
        context_depth=args.context_depth,
        time_budget=args.time_budget,
        reasoning=args.reasoning,
        stream=args.stream,
        idle_timeout=args.idle_timeout,
        sandbox=bool(getattr(args, "sandbox", False)),
        state_dir=getattr(args, "state_dir", None),
        pull_request=getattr(args, "pull_request", None),
        baseline=getattr(args, "baseline", None),
        baseline_from_base=bool(getattr(args, "baseline_from_base", False)),
        baseline_strict=bool(getattr(args, "baseline_strict", False)),
        allow_baseline_change=bool(getattr(args, "allow_baseline_change", False)),
    )


def _bind_pr(args: argparse.Namespace) -> None:
    """Resolve the PR and make its base the review's base. Never checks out."""
    pr: PullRequest = resolve_pr(args.number, args.repo)
    verify_checkout(pr, args.repo)
    args.base = pr.base
    args.pull_request = pr


def _check_output(path: Path, flag: str, *, directory: bool) -> None:
    """Fail before a model call if the output path cannot be written."""
    try:
        if path.is_symlink():
            raise ReviewError(f"{flag} {path} is a symlink; refusing to write through it")
        if path.exists():
            if directory and not path.is_dir():
                raise ReviewError(f"{flag} {path} exists and is not a directory")
            if not directory and path.is_dir():
                raise ReviewError(f"{flag} {path} is a directory; expected a file")
            if not directory and not path.is_file():
                raise ReviewError(f"{flag} {path} is not a regular file")
        parent = path.parent
        if not parent.exists():
            raise ReviewError(f"{flag}: parent directory {parent} does not exist")
        if not parent.is_dir():
            raise ReviewError(f"{flag}: {parent} is not a directory")
        if not os.access(parent, os.W_OK):
            raise ReviewError(f"{flag}: {parent} is not writable")
    except ReviewError:
        raise
    except (OSError, ValueError) as exc:
        raise ReviewError(f"{flag} {path} cannot be used: {exc}") from exc


def _preflight(args: argparse.Namespace) -> None:
    """Everything that can be refused before a run directory or a model call."""
    if args.run_id is not None:
        try:
            validate_run_id(args.run_id)
        except ValueError as exc:
            raise ReviewError(str(exc)) from exc
    if not args.profile.strip():
        raise ReviewError("--profile must not be empty")
    if any(ord(ch) < 32 or 0xD800 <= ord(ch) <= 0xDFFF for ch in args.profile):
        raise ReviewError("--profile must be printable text")
    base = getattr(args, "base", None)
    if base is not None and not base.strip():
        raise ReviewError("--base must not be empty")
    if any(not url.strip() for url in args.context_url):
        raise ReviewError("--context-url must not be empty")
    if args.prompt is not None:
        try:
            if not args.prompt.is_file():
                raise ReviewError(f"no reviewer prompt at {args.prompt}: a review needs an instrument")
            with args.prompt.open("rb") as handle:
                handle.read(1)
        except ReviewError:
            raise
        except (OSError, ValueError) as exc:
            raise ReviewError(f"cannot read the reviewer prompt at {args.prompt}: {exc}") from exc
    if args.baseline is not None and args.baseline_from_base and args.baseline.is_absolute():
        raise ReviewError("--baseline must be repository-relative when read from the base revision")
    if args.baseline_strict and args.baseline is None:
        raise ReviewError("--baseline-strict requires --baseline")
    if args.sarif is not None:
        _check_output(args.sarif, "--sarif", directory=False)
    if args.keep is not None:
        _check_output(args.keep, "--keep", directory=True)


def _review(args: argparse.Namespace) -> Report:
    """Review, and let a person decide when the prompt is over the limit.

    The default is to ask. `--autonomous` (or a pipeline without a terminal)
    never asks: it refuses. `--allow-large-prompt` never asks either: it sends.
    """
    _preflight(args)
    allow = args.allow_large_prompt
    if args.keep is not None:
        args.ephemeral = True
    if args.ephemeral:
        if getattr(args, "ephemeral_root", None) is None:
            try:
                args.ephemeral_root = Path(tempfile.mkdtemp(prefix="council-ephemeral-"))
            except OSError as exc:
                raise ReviewError(f"cannot create a temporary run directory: {exc}") from exc
        if args.run_id is None:
            args.run_id = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        args.state_dir = args.ephemeral_root / args.run_id
    sandbox = args.sandbox
    if sandbox is None:
        sandbox = shutil.which("bwrap") is not None
    if sandbox and shutil.which("bwrap") is None:
        raise ReviewError("--sandbox needs bwrap on PATH; install bubblewrap or use --no-sandbox")
    args.sandbox = sandbox
    runner = hermes_runner(args.profile, binary=args.reviewer,
                           timeout=args.sample_timeout, reasoning=args.reasoning,
                           stream=args.stream, idle_timeout=args.idle_timeout,
                           sandbox=sandbox)
    while True:
        request = _request(args, allow=allow)
        try:
            return review(request, runner)
        except PromptTooLarge as exc:
            interactive = (args.command == "review"
                           and not getattr(args, "autonomous", False)
                           and not allow
                           and sys.stdin.isatty())
            if not interactive:
                raise
            decision, value = _oversize_decision(exc, allow_base=args.command != "pr")
            if decision == "allow":
                allow = True
            elif decision == "budget" and isinstance(value, int):
                args.max_prompt_bytes = value
            elif decision == "base" and isinstance(value, str):
                args.base = value
            elif decision == "context" and isinstance(value, int):
                args.context_depth = value
            else:
                raise PromptTooLarge(exc.size, exc.limit, declined=True) from exc


def _finish_ephemeral(args: argparse.Namespace, report: Report | None) -> None:
    """Copy evidence if asked, then remove the temporary run tree."""
    root = getattr(args, "ephemeral_root", None)
    if root is None:
        return
    keep = getattr(args, "keep", None)
    if keep is not None and report is not None:
        target = Path(keep) / report.run_dir.name
        try:
            source = report.run_dir.resolve()
            resolved = target.resolve()
            if resolved == source or resolved.is_relative_to(source):
                print(f"council: --keep {_safe(target)} is inside the run directory; "
                      f"evidence left at {_safe(report.run_dir)}", file=sys.stderr)
                return
            shutil.copytree(report.run_dir, target)
            print(f"council: kept {_safe(target)}", file=sys.stderr)
        except (OSError, ValueError) as exc:
            print(f"council: could not keep {_safe(target)}: {_safe(exc)}; "
                  f"evidence left at {_safe(report.run_dir)}", file=sys.stderr)
            return
    try:
        shutil.rmtree(root)
    except FileNotFoundError:
        pass
    except OSError as exc:
        print(f"council: could not remove the temporary run tree {_safe(root)}: "
              f"{_safe(exc)}", file=sys.stderr)


def _print_report(report: Report) -> None:
    print(f"{report.verdict.value.upper()}  base {_safe(report.base[:8])} → head {_safe(report.head[:8])}")
    for finding in report.findings:
        print(f"  {_safe(finding.id)}  {_safe(finding.severity):<8} {_safe(finding.dimension):<13} "
              f"{_safe(finding.location)}  {_safe(finding.claim)}")
        print(f"        {finding.state.value} — {_safe(finding.detail)}")
    print(f"  reason: {_safe(report.reason)}")
    if report.gate is not None and report.gate.suppressed:
        print(f"  baseline: {len(report.gate.suppressed)} accepted finding(s)")
    print(f"  run:    {_safe(report.run_dir)}")


def _sarif_result(report: Report) -> Result:
    """SARIF is a report of what still blocks, not the accepted-risk evidence."""
    if report.gate is None or not report.gate.suppressed:
        return report.result
    suppressed = set(report.gate.suppressed)
    return Result(report.gate.verdict, report.gate.reason,
                  tuple(item for item in report.findings if item.id not in suppressed))


def _print_plan(planned: Plan) -> None:
    print(f"PLAN  base {_safe(planned.base[:8])} → head {_safe(planned.head[:8])}")
    stance = "sliced" if planned.sliced else "one prompt"
    print(f"  prompt {planned.prompt_bytes:,} bytes; limit {planned.prompt_limit:,}; {stance}")
    if not planned.sliced:
        print(f"  whole change  {planned.prompt_bytes:,} bytes  context depth {planned.depth}")
    for unit in planned.units:
        files = ", ".join(_safe(name) for name in unit.files)
        print(f"  {_safe(unit.id)}  {files}  {unit.bytes:,} bytes  depth {unit.depth}")
    if planned.skipped:
        listed = ", ".join(f"{_safe(item.path)} ({_safe(item.reason)})"
                           for item in planned.skipped[:5])
        more = f", +{len(planned.skipped) - 5} more" if len(planned.skipped) > 5 else ""
        print(f"  skipped: {len(planned.skipped)} file(s): {listed}{more}")


def _plan_payload(planned: Plan) -> dict[str, object]:
    return {
        "base": planned.base,
        "head": planned.head,
        "prompt_bytes": planned.prompt_bytes,
        "prompt_limit": planned.prompt_limit,
        "sliced": planned.sliced,
        "units": [
            {
                "id": unit.id,
                "files": list(unit.files),
                "ranges": [{"file": file, "start": start, "end": end}
                           for file, start, end in unit.ranges],
                "prompt_bytes": unit.bytes,
                "context_depth": unit.depth,
            }
            for unit in planned.units
        ],
        "skipped": [{"path": item.path, "reason": item.reason} for item in planned.skipped],
    }


def _baseline(args: argparse.Namespace) -> int:
    """Create or prune the accepted-risk file. No reviewer is involved."""
    try:
        today = datetime.now(timezone.utc).date()
        if args.baseline_action == "create":
            expires = today + timedelta(days=args.days)
            baseline = baseline_io.from_run(
                args.from_run, owner=args.owner, reason=args.reason,
                created=today, expires=expires)
            baseline_io.write(args.out, baseline)
            print(f"wrote {args.out} ({len(baseline.entries)} entry/entries, "
                  f"expires {expires.isoformat()})")
            return 0
        baseline = baseline_io.load(args.baseline)
        present = baseline_io.run_fingerprints(args.from_run)
        stale = tuple(entry for entry in baseline.entries
                      if entry.fingerprint not in present)
        if not stale:
            print(f"{args.baseline}: no stale entries")
            return 0
        if args.write:
            baseline_io.write(args.baseline,
                              Baseline(tuple(entry for entry in baseline.entries
                                             if entry.fingerprint in present)))
        verb = "pruned" if args.write else "would prune"
        print(f"{args.baseline}: {verb} {len(stale)} stale entry/entries")
        for entry in stale:
            print(f"  {entry.fingerprint[:12]}  {_safe(entry.file)}:{entry.line}  "
                  f"{_safe(entry.claim)}")
        return 0
    except ReviewError as exc:
        print(f"council: {_safe(exc)}", file=sys.stderr)
        return EXIT_ERROR


def _doctor(args: argparse.Namespace) -> int:
    """Report what this machine can do. A fail is exit 1; a warning is not."""
    runner = hermes_runner(args.profile, binary=args.reviewer,
                           timeout=args.probe_timeout)
    checks = diagnostics.run(args.profile, runner=runner, binary=args.reviewer,
                             probe_timeout=args.probe_timeout)
    if args.json:
        print(json.dumps([asdict(check) for check in checks], indent=2))
    else:
        for check in checks:
            print(check.line())
    return 1 if any(check.status == diagnostics.FAIL for check in checks) else 0


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if getattr(args, "plan", False):
        conflicts = [name for name, value in
                     (("--sarif", getattr(args, "sarif", None)),
                      ("--keep", getattr(args, "keep", None)),
                      ("--report", getattr(args, "report", False)))
                     if value]
        if conflicts:
            print(f"council: --plan writes no run; it cannot be combined with "
                  f"{', '.join(conflicts)}", file=sys.stderr)
            return EXIT_ERROR
        try:
            _preflight(args)
        except ReviewError as exc:
            print(f"council: {_safe(exc)}", file=sys.stderr)
            return EXIT_ERROR

    if args.command == "baseline":
        return _baseline(args)

    if args.command == "doctor":
        return _doctor(args)

    if args.command in ("review", "ci", "pr"):
        try:
            _preflight(args)
        except ReviewError as exc:
            print(f"council: {_safe(exc)}", file=sys.stderr)
            return EXIT_ERROR

    if args.command == "init":
        try:
            added = init_repo(args.repo)
        except ReviewError as exc:
            print(f"council: {_safe(exc)}", file=sys.stderr)
            return EXIT_ERROR
        print("added .council/ to .gitignore" if added else ".council/ is already ignored")
        return 0

    if args.command == "pr":
        try:
            _bind_pr(args)
        except ReviewError as exc:
            print(f"council: {_safe(exc)}", file=sys.stderr)
            return EXIT_ERROR

    if getattr(args, "plan", False):
        try:
            planned = plan(_request(args))
        except (ReviewError, ConfigError) as exc:
            print(f"council: {_safe(exc)}", file=sys.stderr)
            return EXIT_ERROR
        if args.json:
            print(json.dumps(_plan_payload(planned), indent=2))
        else:
            _print_plan(planned)
        return 0

    # Only an interactive `review` asks. `ci` is the autonomous entry point and
    # refuses instead: a pipeline has nobody to read the question.
    try:
        report = _review(args)
    except (ReviewError, ConfigError) as exc:
        _finish_ephemeral(args, None)
        print(f"council: {_safe(exc)}", file=sys.stderr)
        return EXIT_ERROR

    if args.json:
        try:
            print((report.run_dir / "verdict.json").read_text(encoding="utf-8"), end="")
        except (OSError, UnicodeDecodeError) as exc:
            print(f"council: cannot read the verdict at {_safe(report.run_dir)}: "
                  f"{_safe(exc)}", file=sys.stderr)
            _finish_ephemeral(args, report)
            return EXIT_ERROR
    else:
        _print_report(report)

    if args.sarif is not None:
        try:
            args.sarif.write_text(
                json.dumps(render_sarif(_sarif_result(report), tool_version=current_version()),
                           indent=2) + "\n",
                encoding="utf-8", newline="\n")
        except (OSError, ValueError) as exc:
            print(f"council: cannot write SARIF to {_safe(args.sarif)}: {_safe(exc)}",
                  file=sys.stderr)
            _finish_ephemeral(args, report)
            return EXIT_ERROR

    if report.verdict is Verdict.INCOMPLETE:
        stance = "advice only (--report): not blocking here" if args.report \
            else "a merge is blocked until the missing evidence is obtained"
        print(f"council: INCOMPLETE — {stance}", file=sys.stderr)

    if report.skipped:
        listed = ", ".join(f"{item.path} ({item.reason})" for item in report.skipped[:5])
        more = f", +{len(report.skipped) - 5} more" if len(report.skipped) > 5 else ""
        print(f"note: {len(report.skipped)} file(s) in the change were not reviewed: "
              f"{_safe(listed)}{more}", file=sys.stderr)

    if not report.ignored:
        print("note: .council/ is not ignored here; run `council init` to keep git clean",
              file=sys.stderr)

    if getattr(args, "ephemeral", False):
        print("council: ephemeral run; evidence removed after this verdict", file=sys.stderr)
    _finish_ephemeral(args, report)

    return 0 if args.report else report.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
