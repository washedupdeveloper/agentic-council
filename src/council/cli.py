"""The command line: parse, call the deep module, print, exit.

Exit codes are the contract: 0 pass, 1 fail, 2 incomplete, 3 the review could
not be attempted. `--report` turns any non-passing verdict into 0, which is the
advice mode a person wants when they are not gating a merge.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import NoReturn, Sequence

from . import claims as claim_registry
from .run import DEFAULT_PROFILE, DEFAULT_SAMPLES, Report, ReviewError, ReviewRequest, review
from .runner import hermes_runner

EXIT_ERROR = 3


class _Parser(argparse.ArgumentParser):
    """argparse exits 2 on a usage error; 2 already means INCOMPLETE here."""

    def error(self, message: str) -> NoReturn:
        self.print_usage(sys.stderr)
        self.exit(EXIT_ERROR, f"council: {message}\n")


def build_parser() -> argparse.ArgumentParser:
    parser = _Parser(prog="council", description="A review is a claim until a check settles it.")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("review", help="review a change; exits 0/1/2")
    run.add_argument("-C", "--repo", type=Path, default=Path("."),
                     help="repository to review (default: the current directory)")
    run.add_argument("--base", help="revision to diff against (default: origin/HEAD, then HEAD~1)")
    run.add_argument("--samples", type=int, default=DEFAULT_SAMPLES,
                     help=f"reviewer samples to run (default: {DEFAULT_SAMPLES})")
    run.add_argument("--profile", default=DEFAULT_PROFILE, help="Hermes profile to ask")
    run.add_argument("--prompt", type=Path, default=None,
                     help="reviewer prompt to use instead of the one shipped with council")
    run.add_argument("--report", action="store_true",
                     help="advice only: exit 0 whatever the verdict")
    run.add_argument("--json", action="store_true", help="print the run's verdict.json")

    verify = sub.add_parser("verify", help="run every claim in the registry")
    verify.add_argument("--registry", type=Path, default=Path("claims.toml"))
    verify.add_argument("--list", action="store_true", help="list the claims without running them")
    return parser


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

    if args.command == "verify":
        verify_argv = ["--registry", str(args.registry)]
        if args.list:
            verify_argv.append("--list")
        return claim_registry.main(verify_argv)

    try:
        report = review(
            ReviewRequest(repo=args.repo, base=args.base, samples=args.samples,
                          profile=args.profile, prompt=args.prompt),
            hermes_runner(args.profile),
        )
    except ReviewError as exc:
        print(f"council: {exc}", file=sys.stderr)
        return EXIT_ERROR

    if args.json:
        print((report.run_dir / "verdict.json").read_text(encoding="utf-8"), end="")
    else:
        _print_report(report)

    return 0 if args.report else report.exit_code


if __name__ == "__main__":
    raise SystemExit(main())