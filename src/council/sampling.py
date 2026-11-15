"""How many reviewer samples to ask for, and what a unit's evidence means.

The sample policy is a product rule, not run storage. It lives here so a change
to "one clean, two confirm, three tie-break" does not touch the review loop.
"""

from __future__ import annotations

from collections.abc import Sequence

from .findings import Finding, blocks
from .planning import Unit
from .sample import Runner, SampleResult, run_sample
from .verdict import Verdict, judge

AUTO_MAX = 3


def unit_verdict(findings: Sequence[Finding], ok: bool) -> str:
    """The same verdict rule as the run, over one unit's findings."""
    if not ok:
        return Verdict.INCOMPLETE.value
    return judge(findings).verdict.value


def belongs(finding: Finding, unit: Unit) -> bool:
    """Whether a finding's structured place is inside a unit's ranges."""
    if finding.file not in unit.files:
        return False
    if not unit.ranges:
        return True
    return any(file == finding.file and start <= finding.line <= end
               for file, start, end in unit.ranges)


def blocking_key(sample: SampleResult) -> frozenset[tuple[str, str, int, str]] | None:
    """What a sample says would block, independent of wording or proof order."""
    if sample.output is None:
        return None
    return frozenset((item.dimension, item.file, item.line, item.severity)
                     for item in sample.output.findings
                     if blocks(item.dimension, item.severity))


def samples(prompt: str, runner: Runner,
            requested: int | None) -> tuple[tuple[SampleResult, ...], int, bool | None]:
    """Fixed N, or auto: one clean sample, two to confirm a finding, three to break a tie."""
    if requested is not None:
        fixed = tuple(run_sample(prompt, runner, index=index)
                      for index in range(1, requested + 1))
        return fixed, requested, None

    first = run_sample(prompt, runner, index=1)
    if first.output is None:
        # The retry inside `run_sample` already covered a flaky reviewer; asking
        # a missing binary two more times only multiplies the same error.
        return (first,), 1, None
    if not first.output.findings:
        return (first,), 1, True

    results = [first, run_sample(prompt, runner, index=2)]
    agreed: bool | None = (results[1].output is not None
                           and blocking_key(first) == blocking_key(results[1]))
    if not agreed and len(results) < AUTO_MAX:
        results.append(run_sample(prompt, runner, index=3))
        if any(sample.output is None for sample in results):
            agreed = None
        else:
            keys = [blocking_key(sample) for sample in results]
            agreed = len(set(keys)) == 1
    return tuple(results), len(results), agreed
