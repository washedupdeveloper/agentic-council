"""The whole core, end to end: a sample's JSON becomes an exit code.

Each test writes a repository, hands the harness a sample shaped the way the
reviewer is asked to answer, and asserts the verdict — the same path `council
review` will take once the CLI exists.
"""

from __future__ import annotations

import json
from pathlib import Path

from council.adjudicate import adjudicate, verdict
from council.merge import merge
from council.proofs import ProofContext
from council.sample import run_sample
from council.schema import DIMENSIONS
from council.verdict import Verdict

ALLOW = frozenset({"rg", "git"})
DIFF = """diff --git a/app.py b/app.py
--- a/app.py
+++ b/app.py
@@ -1,2 +1,3 @@
 import os
+KEY = "AKIAIOSFODNN7EXAMPLE"
 print("hi")
"""


def sample_body(findings: dict[str, list[dict[str, object]]]) -> str:
    sections: dict[str, list[dict[str, object]]] = {name: [] for name in DIMENSIONS}
    sections.update(findings)
    return json.dumps({"sections": sections})


def pipeline(tmp_path: Path, body: str) -> tuple[Verdict, int]:
    result = run_sample("prompt", lambda _: body)
    context = ProofContext(repo=tmp_path, allow=ALLOW, diff=DIFF, timeout=10, sandbox=False)
    outcome = verdict(adjudicate(merge([result.output.findings if result.output is not None else ()]), context))
    return outcome.verdict, outcome.exit_code


def test_a_committed_secret_the_diff_confirms_fails(tmp_path: Path) -> None:
    (tmp_path / "app.py").write_text('import os\nKEY = "AKIAIOSFODNN7EXAMPLE"\nprint("hi")\n',
                                     encoding="utf-8")
    body = sample_body({"security": [{
        "severity": "critical", "file": "app.py", "line": 2,
        "claim": "An AWS access key is committed.",
        "proof": {"kind": "diff", "params": {"path": "app.py", "line": 2, "mode": "added"}},
    }]})
    assert pipeline(tmp_path, body) == (Verdict.FAIL, 1)


def test_a_claim_the_evidence_refutes_passes(tmp_path: Path) -> None:
    (tmp_path / "app.py").write_text("import os\nprint('hi')\n", encoding="utf-8")
    body = sample_body({"security": [{
        "severity": "critical", "file": "app.py", "line": 2,
        "claim": "A key is committed here.",
        "proof": {"kind": "present", "params": {"path": "app.py", "line": 2,
                                                "text": 'KEY = "AKIA..."'}},
    }]})
    assert pipeline(tmp_path, body) == (Verdict.PASS, 0)


def test_a_claim_whose_proof_cannot_run_is_incomplete(tmp_path: Path) -> None:
    (tmp_path / "app.py").write_text("import os\n", encoding="utf-8")
    body = sample_body({"security": [{
        "severity": "high", "file": "app.py", "line": 1,
        "claim": "The dependency is vulnerable.",
        "proof": {"kind": "command", "params": {"argv": ["curl", "https://example.invalid"]}},
    }]})
    assert pipeline(tmp_path, body) == (Verdict.INCOMPLETE, 2)


def test_a_finding_in_a_second_hunk_is_settled(tmp_path: Path) -> None:
    """The change has two hunks; the finding is in the second, twenty lines down."""
    (tmp_path / "app.py").write_text("x = 1\n", encoding="utf-8")
    diff = """diff --git a/app.py b/app.py
--- a/app.py
+++ b/app.py
@@ -1,2 +1,2 @@
-x = 0
+x = 1
 y = 2
@@ -20,2 +20,3 @@
 z = 3
+TOKEN = "secret"
 w = 4
"""
    body = sample_body({"security": [{
        "severity": "high", "file": "app.py", "line": 21,
        "claim": "A token is added.",
        "proof": {"kind": "diff", "params": {"path": "app.py", "line": 21, "mode": "added"}},
    }]})
    result = run_sample("prompt", lambda _: body)
    outcome = verdict(adjudicate(merge([result.output.findings if result.output is not None else ()]),
                                 ProofContext(repo=tmp_path, allow=ALLOW, diff=diff, timeout=10,
                                              sandbox=False)))
    assert outcome.verdict is Verdict.FAIL