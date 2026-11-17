"""Human and machine renderings of a plan or a report.

Model output is sanitized here, once, before it can reach a terminal. The JSON
plan payload is part of the CLI contract and stays next to its printer.
"""

from __future__ import annotations

from .domain.text import sanitize
from .planning import Plan
from .run import Report
from .domain.verdict import Result


def safe(text: object) -> str:
    """One printable line: model output must not drive the terminal."""
    return sanitize(text)


def print_report(report: Report) -> None:
    print(f"{report.verdict.value.upper()}  base {safe(report.base[:8])} → head {safe(report.head[:8])}")
    for finding in report.findings:
        print(f"  {safe(finding.id)}  {safe(finding.severity):<8} {safe(finding.dimension):<13} "
              f"{safe(finding.location)}  {safe(finding.claim)}")
        print(f"        {finding.state.value} — {safe(finding.detail)}")
    print(f"  reason: {safe(report.reason)}")
    if report.gate is not None and report.gate.suppressed:
        print(f"  baseline: {len(report.gate.suppressed)} accepted finding(s)")
    print(f"  run:    {safe(report.run_dir)}")


def sarif_result(report: Report) -> Result:
    """SARIF is a report of what still blocks, not the accepted-risk evidence."""
    return report.effective


def print_plan(planned: Plan) -> None:
    print(f"PLAN  base {safe(planned.base[:8])} → head {safe(planned.head[:8])}")
    stance = "sliced" if planned.sliced else "one prompt"
    print(f"  prompt {planned.prompt_bytes:,} bytes; limit {planned.prompt_limit:,}; {stance}")
    if not planned.sliced:
        print(f"  whole change  {planned.prompt_bytes:,} bytes  context depth {planned.depth}")
    for unit in planned.units:
        files = ", ".join(safe(name) for name in unit.files)
        window = (f"  lines {unit.ranges[0][1]}–{unit.ranges[0][2]}"
                  if unit.window and unit.ranges else "")
        print(f"  {safe(unit.id)}  {files}{window}  {unit.bytes:,} bytes  depth {unit.depth}")
    if planned.rules:
        paths = sum(len(hit.paths) for hit in planned.rules)
        print(f"  rules: {len(planned.rules)} document(s) govern {paths} changed file(s)")
    if planned.windows:
        low, high = planned.estimated_samples
        print(f"  windows: {planned.windows} of {len(planned.units)} unit(s): "
              f"{low:,}–{high:,} sample(s) expected")
    if planned.skipped:
        listed = ", ".join(f"{safe(item.path)} ({safe(item.reason)})"
                           for item in planned.skipped[:5])
        more = f", +{len(planned.skipped) - 5} more" if len(planned.skipped) > 5 else ""
        print(f"  skipped: {len(planned.skipped)} file(s): {listed}{more}")
    if planned.scope_ignored:
        listed = ", ".join(f"{safe(item.path)} ({safe(item.reason)})"
                           for item in planned.scope_ignored[:5])
        more = (f", +{len(planned.scope_ignored) - 5} more"
                if len(planned.scope_ignored) > 5 else "")
        print(f"  outside scope: {len(planned.scope_ignored)} file(s): {listed}{more}")


def plan_payload(planned: Plan) -> dict[str, object]:
    return {
        "base": planned.base,
        "head": planned.head,
        "scope": {"include": list(planned.scope_include),
                  "exclude": list(planned.scope_exclude)},
        "prompt_bytes": planned.prompt_bytes,
        "prompt_limit": planned.prompt_limit,
        "sliced": planned.sliced,
        "windows": planned.windows,
        "rules": [{"glob": hit.glob, "doc": hit.doc, "paths": list(hit.paths),
                   "truncated": hit.truncated} for hit in planned.rules],
        "estimated_samples": list(planned.estimated_samples),
        "units": [
            {
                "id": unit.id,
                "files": list(unit.files),
                "ranges": [{"file": file, "start": start, "end": end}
                           for file, start, end in unit.ranges],
                "prompt_bytes": unit.bytes,
                "context_depth": unit.depth,
                "window": unit.window,
            }
            for unit in planned.units
        ],
        "skipped": [{"path": item.path, "reason": item.reason} for item in planned.skipped],
        "scope_ignored": [
            {"path": item.path, "reason": item.reason, "pattern": item.pattern}
            for item in planned.scope_ignored
        ],
    }
