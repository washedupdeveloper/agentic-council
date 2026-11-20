"""The command-line surface: argument shapes and defaults, nothing else.

`cli.py` keeps the orchestration; this module owns `argparse` so help text,
defaults and parsing can be read (and tested) without importing the review
pipeline.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import NoReturn

from .agents import DEFAULT_AGENT
from .request import DEFAULT_PROFILE, PROMPT_LIMIT, WINDOW_LIMIT
from .runner import DEFAULT_IDLE_TIMEOUT
from .version import current_version

EXIT_ERROR = 3


def positive(value: str) -> int:
    try:
        number = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("expected a positive number") from exc
    if number < 1:
        raise argparse.ArgumentTypeError("expected at least 1")
    return number


def samples(value: str) -> int | None:
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


def path(value: str) -> Path:
    if not value.strip():
        raise argparse.ArgumentTypeError("expected a path, not an empty string")
    return Path(value)


def non_negative(value: str) -> int:
    try:
        number = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("expected a non-negative number") from exc
    if number < 0:
        raise argparse.ArgumentTypeError("expected 0 or more")
    return number


class Parser(argparse.ArgumentParser):
    """argparse exits 2 on a usage error; 2 already means INCOMPLETE here."""

    def error(self, message: str) -> NoReturn:
        self.print_usage(sys.stderr)
        self.exit(EXIT_ERROR, f"council: {message}\n")


def add_review_arguments(parser: argparse.ArgumentParser, *, advice: bool,
                         base: bool = True, staged: bool = True) -> None:
    """The review surface, shared by `review` and `ci`.

    `ci` is the gate without the advice switches: it always prints the verdict
    as JSON and always exits with it. A CI entry that could be told to exit 0
    is not a gate.
    """
    parser.add_argument("-C", "--repo", type=path, default=Path("."),
                        help="repository to review (default: the current directory)")
    if base:
        parser.add_argument("--base", help="revision to diff against (default: origin/HEAD, then HEAD~1)")
    if staged:
        parser.add_argument("--staged", action="store_true",
                            help="review the index against the base, not the working tree")
    parser.add_argument("--include", action="append", default=[], metavar="GLOB",
                        help="review only paths matching GLOB (repeatable; caller-owned)")
    parser.add_argument("--exclude", action="append", default=[], metavar="GLOB",
                        help="never review paths matching GLOB (repeatable; exclude wins)")
    parser.add_argument("--samples", type=samples, default=None,
                        help="samples: N, or auto (default: 1 clean, 2 to confirm, 3 to break a tie); per unit when sliced")
    parser.add_argument("--agent", default=DEFAULT_AGENT,
                        help="reviewer adapter to use (default: hermes)")
    parser.add_argument("--profile", default=DEFAULT_PROFILE, help="profile for an adapter that uses one (Hermes)")
    parser.add_argument("--reviewer", default=None,
                        help="executable for the selected adapter (default: the adapter's default)")
    parser.add_argument("--sample-timeout", type=positive, default=900, metavar="SECONDS",
                        help="give up on one sample after N seconds (default: 900)")
    parser.add_argument("--time-budget", type=non_negative, default=0, metavar="SECONDS",
                        help="stop starting units after N seconds (default: 0, no budget)")
    parser.add_argument("--reasoning", default=None,
                        choices=("none", "minimal", "low", "medium", "high",
                                 "xhigh", "max", "ultra"),
                        help="reasoning effort for this review (default: the profile's setting)")
    parser.add_argument("--stream", action=argparse.BooleanOptionalAction, default=True,
                        help="read the reviewer as JSON events and kill a silent stream (default: on)")
    parser.add_argument("--idle-timeout", type=positive, default=DEFAULT_IDLE_TIMEOUT,
                        metavar="SECONDS",
                        help="kill a stream with no event for N seconds (default: 120)")
    parser.add_argument("--sandbox", action=argparse.BooleanOptionalAction, default=None,
                        help="run the reviewer in a bwrap sandbox (default: on when bwrap is available)")
    parser.add_argument("--ephemeral", action=argparse.BooleanOptionalAction, default=True,
                        help="keep run state in a temp tree and remove it (default); "
                             "--no-ephemeral writes .council/runs")
    parser.add_argument("--keep", type=path, default=None, metavar="DIR",
                        help="copy the run directory here before the ephemeral tree is removed")
    parser.add_argument("--prompt", type=path, default=None,
                        help="reviewer prompt to use instead of the one shipped with council")
    parser.add_argument("--sarif", type=path, default=None, metavar="PATH",
                        help="also write proven findings as a SARIF 2.1.0 log")
    parser.add_argument("--run-id", default=None,
                        help="name this run instead of using a timestamp (refused if it exists)")
    parser.add_argument("--baseline", type=path, default=None, metavar="PATH",
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
    parser.add_argument("--max-prompt-bytes", type=positive, default=PROMPT_LIMIT,
                        metavar="N",
                        help="refuse a prompt larger than N bytes (default: 32768)")
    parser.add_argument("--allow-large-prompt", action="store_true",
                        help="send an oversized prompt without asking (autonomous allow)")
    parser.add_argument("--window-large-files", action="store_true",
                        help="split a file too large for one prompt into line windows "
                             "(one sample per window; refused by default)")
    parser.add_argument("--max-windows", type=positive, default=WINDOW_LIMIT, metavar="N",
                        help="refuse a change that would need more than N windows "
                             "(default: 200)")
    parser.add_argument("--require-executed-proofs", action="store_true",
                        help="a finding proven only by quotation cannot block the run "
                             "(default: it blocks, and the reason says so)")
    if advice:
        parser.add_argument("--autonomous", action="store_true",
                            help="never ask: refuse an oversized prompt, exit 3")
        parser.add_argument("--plan", action="store_true",
                            help="show units and prompt sizes; call no reviewer and write no run")
        parser.add_argument("--report", action="store_true",
                            help="advice only: exit 0 whatever the verdict")
        parser.add_argument("--json", action="store_true", help="print the run's verdict.json")


def build_parser() -> argparse.ArgumentParser:
    parser = Parser(prog="council",
                    description="A review is a claim until a check settles it.")
    parser.add_argument("--version", action="version",
                        version=f"%(prog)s {current_version()}")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("review", help="review a change; exits 0/1/2")
    add_review_arguments(run, advice=True)

    ci = sub.add_parser("ci", help="the gate for CI: prints verdict.json, exits 0/1/2")
    add_review_arguments(ci, advice=False)
    ci.set_defaults(report=False, json=True, baseline_from_base=True)

    pr = sub.add_parser("pr", help="review a GitHub pull request by number, URL or branch")
    pr.add_argument("target", help="pull request number, URL, or branch")
    add_review_arguments(pr, advice=True, base=False, staged=False)
    pr.set_defaults(baseline_from_base=True)

    baseline = sub.add_parser("baseline", help="create or prune an accepted-risk baseline")
    baseline_sub = baseline.add_subparsers(dest="baseline_action", required=True)
    create = baseline_sub.add_parser("create", help="snapshot proven blocking findings from a run")
    create.add_argument("--from", dest="from_run", type=path, required=True, metavar="DIR",
                        help="kept run directory containing verdict.json")
    create.add_argument("--out", type=path, required=True, metavar="PATH")
    create.add_argument("--owner", required=True, help="person or team accepting the risk")
    create.add_argument("--reason", required=True, help="why the accepted risk is tolerated")
    create.add_argument("--days", type=positive, default=90, metavar="N",
                        help="days until the accepted risk expires (default: 90)")
    prune = baseline_sub.add_parser("prune", help="remove entries no longer found in a run")
    prune.add_argument("--baseline", type=path, required=True, metavar="PATH")
    prune.add_argument("--from", dest="from_run", type=path, required=True, metavar="DIR")
    prune.add_argument("--write", action="store_true",
                       help="write the pruned baseline (default: report only)")

    init = sub.add_parser("init", help="add .council/ to the repository's .gitignore")
    init.add_argument("-C", "--repo", type=path, default=Path("."),
                      help="repository to initialize (default: the current directory)")

    agents = sub.add_parser("agents", help="list reviewer adapters available in this build")
    agents.add_argument("--json", action="store_true", help="print the adapter list as JSON")

    evidence = sub.add_parser("evidence", help="attach local screenshots to a kept run")
    evidence_sub = evidence.add_subparsers(dest="evidence_action", required=True)
    for action, description in (("add", "copy screenshot(s) into a run"),
                                ("list", "show the run's screenshots as direct links")):
        item = evidence_sub.add_parser(action, help=description)
        item.add_argument("run_id", help="retained run id")
        if action == "add":
            item.add_argument("files", nargs="+", type=path, metavar="IMAGE",
                              help="screenshot or other local evidence file")
            item.add_argument("--label", default="",
                              help="text for the direct link (default: the file name)")
        item.add_argument("-C", "--repo", type=path, default=Path("."),
                          help="repository whose .council/runs is searched (default: current)")
        item.add_argument("--state-root", type=path, default=None, metavar="DIR",
                          help="directory containing retained run ids (e.g. the ACP cache)")
        item.add_argument("--json", action="store_true", help="print links and metadata as JSON")

    doctor = sub.add_parser("doctor", help="check that this machine can run a review")
    doctor.add_argument("--agent", default=DEFAULT_AGENT,
                        help="reviewer adapter to check (default: hermes)")
    doctor.add_argument("--profile", default=DEFAULT_PROFILE, help="profile for an adapter that uses one (Hermes)")
    doctor.add_argument("--reviewer", default=None,
                        help="executable for the selected adapter (default: the adapter's default)")
    doctor.add_argument("--probe-timeout", type=positive, default=60, metavar="SECONDS",
                        help="how long the profile has to answer the probe (default: 60)")
    doctor.add_argument("--json", action="store_true", help="print the checks as JSON")

    setup = sub.add_parser("setup", help="install this tool's skills from a skill library")
    setup_sub = setup.add_subparsers(dest="setup_action", required=True)
    skill = setup_sub.add_parser(
        "skill", help="install skill(s) from a library into an agent's skills directory")
    skill.add_argument("names", nargs="*", metavar="NAME",
                       help="skills to install (see --list for what the library holds)")
    skill.add_argument("--library", type=path, metavar="DIR",
                       help="skill library root (default: $SKILLS_LIBRARY, else the "
                            "nearest directory holding library/contract.json)")
    skill.add_argument("--dest", type=path, metavar="DIR",
                       help="skills directory to install into (default: $SKILLS_DIR, "
                            "else the one --agent resolves to)")
    skill.add_argument("--agent",
                       help="fill --dest from an agent's conventional skills directory")
    skill.add_argument("--list", action="store_true",
                       help="print the library's skills and exit")
    skill.add_argument("--force", action="store_true",
                       help="replace a skill that differs")
    skill.add_argument("--dry-run", action="store_true",
                       help="report what would happen and write nothing")
    return parser
