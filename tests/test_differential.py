"""The differential is a pinned expectation, so it is tested like one."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def run() -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, "tools/differential.py"], cwd=ROOT,
                          capture_output=True, text=True)


def test_it_accepts_the_fixtures_and_explains_the_difference() -> None:
    result = run()
    assert result.returncode == 0, result.stdout + result.stderr
    assert "defects" in result.stdout and "INCOMPLETE" in result.stdout
    assert "never checked" in result.stdout


def test_the_defects_round_has_four_blocking_claims_and_no_check() -> None:
    line = next(line for line in run().stdout.splitlines() if line.startswith("defects"))
    fields = line.split()
    assert fields[2] == "INCOMPLETE"
    assert fields[4] == "4"      # blocking: severity high+, or security/correctness at any severity
    assert fields[5] == "0"      # with a check