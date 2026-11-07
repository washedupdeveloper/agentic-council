"""One sample: run, parse, retry once, record. A failure is recorded, not
dropped."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .schema import ReviewerOutput, SchemaError, parse_reviewer_output

#: prompt -> the model's raw text. Raising `OSError` means the reviewer could not run.
Runner = Callable[[str], str]

ATTEMPTS = 2


@dataclass(frozen=True, slots=True)
class SampleResult:
    index: int
    output: ReviewerOutput | None
    attempts: int
    error: str | None

    @property
    def ok(self) -> bool:
        return self.output is not None


def run_sample(prompt: str, runner: Runner, *, index: int = 1,
               attempts: int = ATTEMPTS) -> SampleResult:
    """Run one sample, retrying a failure up to `attempts` times in total."""
    if attempts < 1:
        raise ValueError("attempts must be at least 1")

    last = "no attempt was made"
    for attempt in range(1, attempts + 1):
        try:
            text = runner(prompt)
        except OSError as exc:
            last = f"the reviewer could not run: {exc}"
            continue
        try:
            return SampleResult(index, parse_reviewer_output(text), attempt, None)
        except SchemaError as exc:
            last = str(exc)
    return SampleResult(index, None, attempts, last)


def write_sample(run_dir: Path, result: SampleResult) -> Path:
    """Write the sample beside the run, in the same shape whatever happened."""
    run_dir.mkdir(parents=True, exist_ok=True)
    path = run_dir / f"sample-{result.index}.json"
    findings = result.output.findings if result.output is not None else ()
    payload: dict[str, object] = {
        "index": result.index,
        "attempts": result.attempts,
        "error": result.error,
        "findings": [
            {
                "dimension": finding.dimension,
                "severity": finding.severity,
                "file": finding.file,
                "line": finding.line,
                "claim": finding.claim,
                "proof": {"kind": finding.proof_kind, "params": finding.proof_params},
            }
            for finding in findings
        ],
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8", newline="\n")
    return path