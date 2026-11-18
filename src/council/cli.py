"""CLI: 0 pass, 1 fail, 2 incomplete, 3 could not start. `--report` exits 0."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
from collections.abc import Sequence
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from pathlib import Path

from . import baseline as baseline_io
from . import doctor as diagnostics
from .cli_output import plan_payload as _plan_payload
from .cli_output import print_plan as _print_plan
from .cli_output import print_report as _print_report
from .cli_output import safe as _safe
from .cli_output import sarif_result as _sarif_result
from .cli_parser import EXIT_ERROR, build_parser
from .config import ConfigError
from .domain.baseline import Baseline, stale_fingerprints
from .planning import Plan  # noqa: F401 - re-exported for callers and tests
from .pr import PullRequest, verify_checkout
from .pr import resolve as resolve_pr
from .repo import ReviewError
from .repo import init as init_repo
from .run import (
    PromptTooLarge,
    Report,
    ReviewRequest,
    plan,
    review,
)
from .runner import hermes_runner
from .domain.sarif import render as render_sarif
from .domain.verdict import Verdict
from .version import current_version

_OVERSIZE_HELP = """\
council: why there is a limit
  A prompt above the limit is not sent. A model can sit on a large prompt until
  its timeout and be retried once: that looks like a hang and costs the whole
  wait. Measured with this provider: a 2.8 KB prompt was answered; a 60 KB
  prompt was not. The limit is a starting point, not a rule — raise it for this
  run, or narrow the change with a base revision.

  A file too large to send at any depth can be split into line windows instead
  (`window`, or --window-large-files). Each window is its own sample, so the cost
  is the window count and not the file: a 38,000-line addition is tens of
  windows, which is hours. That is why the default refuses, and why the count is
  printed before the choice.
"""

_OVERSIZE_ADVICE = ("narrow the change with --base, raise the budget with "
                    "--max-prompt-bytes, split it with --window-large-files, or allow "
                    "it with --allow-large-prompt")


def _oversize_decision(exc: PromptTooLarge, *, allow_base: bool = True,
                       allow_window: bool = True) -> tuple[str, int | str | None]:
    """Ask a person what to do. Empty input or EOF cancels: silence is not consent."""
    while True:
        print(f"council: the prompt for this change is {exc.size:,} bytes; "
              f"the limit is {exc.limit:,}.", file=sys.stderr)
        if exc.windows:
            print(f"council: split into line windows it would be {exc.windows:,} unit(s): "
                  f"{exc.windows:,}–{exc.windows * 3:,} sample(s), one per window. The wait "
                  "grows with that count, not with the file.", file=sys.stderr)
        print("council: nothing has been sent to the model. how should this proceed?",
              file=sys.stderr)
        window = ("  window          split it into line windows, one sample each\n"
                  if exc.windows and allow_window else "")
        print("  allow           send it anyway\n"
              "  budget N        set the limit to N bytes and retry\n"
              "  base REV        review a narrower change\n"
              "  context N       layers: 0 none, 1 enclosing, 2 +1 call, 3 +2\n"
              + window +
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
        if command == "window":
            if not exc.windows or not allow_window:
                print("council: splitting is not available for this change", file=sys.stderr)
                continue
            return ("window", None)
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
        repo=args.repo, base=getattr(args, "base", None), samples=args.samples,
        profile=args.profile, prompt=args.prompt, run_id=args.run_id,
        context_urls=tuple(args.context_url),
        allow_large_prompt=args.allow_large_prompt if allow is None else allow,
        max_prompt_bytes=args.max_prompt_bytes,
        window_large_files=bool(getattr(args, "window_large_files", False)),
        max_windows=int(getattr(args, "max_windows", 200)),
        require_executed_proofs=bool(getattr(args, "require_executed_proofs", False)),
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
        include=tuple(getattr(args, "include", ())),
        exclude=tuple(getattr(args, "exclude", ())),
        staged=bool(getattr(args, "staged", False)),
    )


def _bind_pr(args: argparse.Namespace) -> None:
    """Resolve the PR and make its base the review's base. Never checks out."""
    pr: PullRequest = resolve_pr(args.target, args.repo)
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
    try:
        _request(args).validate()
    except ValueError as exc:
        raise ReviewError(str(exc)) from exc
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
            args.run_id = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
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
            decision, value = _oversize_decision(
                exc, allow_base=args.command != "pr",
                allow_window=not bool(getattr(args, "window_large_files", False)))
            if decision == "allow":
                allow = True
            elif decision == "window":
                args.window_large_files = True
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


def _baseline(args: argparse.Namespace) -> int:
    """Create or prune the accepted-risk file. No reviewer is involved."""
    try:
        today = datetime.now(UTC).date()
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
        stale = stale_fingerprints(baseline, present)
        stale_set = set(stale)
        if not stale:
            print(f"{args.baseline}: no stale entries")
            return 0
        if args.write:
            baseline_io.write(args.baseline,
                              Baseline(tuple(entry for entry in baseline.entries
                                             if entry.fingerprint not in stale_set)))
        verb = "pruned" if args.write else "would prune"
        print(f"{args.baseline}: {verb} {len(stale)} stale entry/entries")
        for entry in (item for item in baseline.entries
                          if item.fingerprint in stale_set):
            print(f"  {entry.fingerprint[:12]}  {_safe(entry.file)}:{entry.line}  "
                  f"{_safe(entry.claim)}")
        return 0
    except ReviewError as exc:
        print(f"council: {_safe(exc)}", file=sys.stderr)
        return EXIT_ERROR


def _setup(args: object) -> int:
    """`setup skill`: install from a library. Refusals are exit 3, like every other."""
    from .skill_install import SkillSetupError
    from .skill_install import run as run_setup

    try:
        return run_setup(args)
    except SkillSetupError as exc:
        print(f"council: {exc}", file=sys.stderr)
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
    except PromptTooLarge as exc:
        _finish_ephemeral(args, None)
        print(f"council: {_safe(exc)}", file=sys.stderr)
        if not exc.declined:
            print(f"council: {_OVERSIZE_ADVICE}", file=sys.stderr)
        return EXIT_ERROR
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
    if report.scope_ignored:
        listed = ", ".join(f"{item.path} ({item.reason})" for item in report.scope_ignored[:5])
        more = (f", +{len(report.scope_ignored) - 5} more"
                if len(report.scope_ignored) > 5 else "")
        print(f"note: {len(report.scope_ignored)} file(s) were outside the caller's "
              f"scope and were not reviewed: {_safe(listed)}{more}", file=sys.stderr)

    if not report.ignored:
        print("note: .council/ is not ignored here; run `council init` to keep git clean",
              file=sys.stderr)

    if getattr(args, "ephemeral", False):
        print("council: ephemeral run; evidence removed after this verdict", file=sys.stderr)
    _finish_ephemeral(args, report)

    return 0 if args.report else report.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
