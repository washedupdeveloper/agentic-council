"""CLI: 0 pass, 1 fail, 2 incomplete, 3 could not start. `--report` exits 0."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import NoReturn, Sequence

from .config import ConfigError
from .repo import ReviewError, init as init_repo
from .run import DEFAULT_PROFILE, PROMPT_LIMIT, PromptTooLarge, Report, ReviewRequest, review
from .runner import hermes_runner
from .verdict import Verdict

EXIT_ERROR = 3


def _positive(value: str) -> int:
    try:
        number = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("expected a number of bytes") from exc
    if number < 1:
        raise argparse.ArgumentTypeError("expected at least 1 byte")
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


class _Parser(argparse.ArgumentParser):
    """argparse exits 2 on a usage error; 2 already means INCOMPLETE here."""

    def error(self, message: str) -> NoReturn:
        self.print_usage(sys.stderr)
        self.exit(EXIT_ERROR, f"council: {message}\n")


def _add_review_arguments(parser: argparse.ArgumentParser, *, advice: bool) -> None:
    """The review surface, shared by `review` and `ci`.

    `ci` is the gate without the advice switches: it always prints the verdict
    as JSON and always exits with it. A CI entry that could be told to exit 0
    is not a gate.
    """
    parser.add_argument("-C", "--repo", type=Path, default=Path("."),
                        help="repository to review (default: the current directory)")
    parser.add_argument("--base", help="revision to diff against (default: origin/HEAD, then HEAD~1)")
    parser.add_argument("--samples", type=_samples, default=None,
                        help="samples: N, or auto (default: 1 clean, 2 to confirm, 3 to break a tie); per unit when sliced")
    parser.add_argument("--profile", default=DEFAULT_PROFILE, help="Hermes profile to ask")
    parser.add_argument("--reviewer", default="hermes",
                        help="binary that answers a sample (default: hermes)")
    parser.add_argument("--sample-timeout", type=_positive, default=900, metavar="SECONDS",
                        help="give up on one sample after N seconds (default: 900)")
    parser.add_argument("--prompt", type=Path, default=None,
                        help="reviewer prompt to use instead of the one shipped with council")
    parser.add_argument("--run-id", default=None,
                        help="name this run instead of using a timestamp (refused if it exists)")
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
        parser.add_argument("--report", action="store_true",
                            help="advice only: exit 0 whatever the verdict")
        parser.add_argument("--json", action="store_true", help="print the run's verdict.json")


def build_parser() -> argparse.ArgumentParser:
    parser = _Parser(prog="council", description="A review is a claim until a check settles it.")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("review", help="review a change; exits 0/1/2")
    _add_review_arguments(run, advice=True)

    ci = sub.add_parser("ci", help="the gate for CI: prints verdict.json, exits 0/1/2")
    _add_review_arguments(ci, advice=False)
    ci.set_defaults(report=False, json=True)

    init = sub.add_parser("init", help="add .council/ to the repository's .gitignore")
    init.add_argument("-C", "--repo", type=Path, default=Path("."))
    return parser


_OVERSIZE_HELP = """\
council: why there is a limit
  A prompt above the limit is not sent. A model can sit on a large prompt until
  its timeout and be retried once: that looks like a hang and costs the whole
  wait. Measured with this provider: a 2.8 KB prompt was answered; a 60 KB
  prompt was not. The limit is a starting point, not a rule — raise it for this
  run, or narrow the change with a base revision.
"""


def _oversize_decision(exc: PromptTooLarge) -> tuple[str, int | str | None]:
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
        line = sys.stdin.readline()
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


def _review(args: argparse.Namespace) -> Report:
    """Review, and let a person decide when the prompt is over the limit.

    The default is to ask. `--autonomous` (or a pipeline without a terminal)
    never asks: it refuses. `--allow-large-prompt` never asks either: it sends.
    """
    allow = args.allow_large_prompt
    runner = hermes_runner(args.profile, binary=args.reviewer,
                           timeout=args.sample_timeout)
    while True:
        request = ReviewRequest(repo=args.repo, base=args.base, samples=args.samples,
                                profile=args.profile, prompt=args.prompt,
                                run_id=args.run_id, context_urls=tuple(args.context_url),
                                allow_large_prompt=allow,
                                max_prompt_bytes=args.max_prompt_bytes,
                                context_depth=args.context_depth)
        try:
            return review(request, runner)
        except PromptTooLarge as exc:
            interactive = (args.command == "review"
                           and not getattr(args, "autonomous", False)
                           and not allow
                           and sys.stdin.isatty())
            if not interactive:
                raise
            decision, value = _oversize_decision(exc)
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


def _print_report(report: Report) -> None:
    print(f"{report.verdict.value.upper()}  base {report.base[:8]} → head {report.head[:8]}")
    for finding in report.findings:
        print(f"  {finding.id}  {finding.severity:<8} {finding.dimension:<13} "
              f"{finding.location}  {finding.claim}")
        print(f"        {finding.state.value} — {finding.detail}")
    print(f"  reason: {report.result.reason}")
    print(f"  run:    {report.run_dir}")


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.command == "init":
        try:
            added = init_repo(args.repo)
        except ReviewError as exc:
            print(f"council: {exc}", file=sys.stderr)
            return EXIT_ERROR
        print("added .council/ to .gitignore" if added else ".council/ is already ignored")
        return 0

    # Only an interactive `review` asks. `ci` is the autonomous entry point and
    # refuses instead: a pipeline has nobody to read the question.
    try:
        report = _review(args)
    except (ReviewError, ConfigError) as exc:
        print(f"council: {exc}", file=sys.stderr)
        return EXIT_ERROR

    if args.json:
        print((report.run_dir / "verdict.json").read_text(encoding="utf-8"), end="")
    else:
        _print_report(report)

    if report.verdict is Verdict.INCOMPLETE:
        stance = "advice only (--report): not blocking here" if args.report \
            else "a merge is blocked until the missing evidence is obtained"
        print(f"council: INCOMPLETE — {stance}", file=sys.stderr)

    if report.skipped:
        listed = ", ".join(f"{item.path} ({item.reason})" for item in report.skipped[:5])
        more = f", +{len(report.skipped) - 5} more" if len(report.skipped) > 5 else ""
        print(f"note: {len(report.skipped)} file(s) in the change were not reviewed: "
              f"{listed}{more}", file=sys.stderr)

    if not report.ignored:
        print("note: .council/ is not ignored here; run `council init` to keep git clean",
              file=sys.stderr)

    return 0 if args.report else report.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
