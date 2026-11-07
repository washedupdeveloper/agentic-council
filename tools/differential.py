"""v1.9.0's pinned verdicts beside v2's rule, on the same fixtures.

Every defect in v1's golden round says `falsifiable_check: "see the claim"`, so
v1 failed a run on claims it never checked. v2 makes those UNSETTLED, so the
same fixture is INCOMPLETE, not FAIL. That difference is the point.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from council.findings import Finding, State  # noqa: E402
from council.verdict import Verdict, judge  # noqa: E402

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "golden"
PLACEHOLDER = "see the claim"
SEVERITIES = {"low", "medium", "high", "critical"}
EXPECTED = {"clean": Verdict.PASS, "defects": Verdict.INCOMPLETE}


@dataclass(frozen=True, slots=True)
class Round:
    name: str
    v1: str
    verdict: Verdict
    findings: int
    blocking: int
    checkable: int
    unmappable: int


def _items(name: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for path in sorted((FIXTURES / "rounds" / name).glob("*.json")):
        out += json.loads(path.read_text(encoding="utf-8")).get("findings", [])
    return out


def compare() -> list[Round]:
    pinned = json.loads((FIXTURES / "expect.json").read_text(encoding="utf-8"))["rounds"]
    rounds: list[Round] = []
    for name in ("clean", "defects"):
        items = _items(name)
        mapped: list[Finding] = []
        checkable = unmappable = 0
        for item in items:
            severity = item.get("severity", "medium")
            if severity not in SEVERITIES:
                unmappable += 1
                continue
            checkable += item.get("falsifiable_check", PLACEHOLDER) != PLACEHOLDER
            mapped.append(Finding(id=item.get("id", "?"), dimension=item.get("dimension", "?"),
                                  severity=severity, state=State.UNSETTLED))
        rounds.append(Round(name, pinned[name]["status"], judge(mapped).verdict, len(items),
                            sum(f.blocks for f in mapped), checkable, unmappable))
    return rounds


def main() -> int:
    rounds = compare()
    print(f"{'round':8} {'v1':14} {'v2':12} {'findings':9} {'blocking':9} {'checked':8} unmappable")
    for r in rounds:
        print(f"{r.name:8} {r.v1:14} {r.verdict.name:12} {r.findings:<9} {r.blocking:<9} "
              f"{r.checkable:<8} {r.unmappable}")

    problems = []
    for r in rounds:
        if r.verdict is not EXPECTED[r.name]:
            problems.append(f"{r.name}: v2 gave {r.verdict.name}, expected {EXPECTED[r.name].name}")
        if r.checkable:
            problems.append(f"{r.name}: {r.checkable} finding(s) carry a check; "
                            "the differential can settle them now")
    if problems:
        print("\n".join(["", *problems]))
        return 1
    print("\nclean PASS == v1 satisfied; defects INCOMPLETE != v1 not_satisfied, "
          "because v1 failed claims it never checked.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())