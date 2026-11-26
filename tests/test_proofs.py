"""Each proof kind, in both directions, plus what cannot run.

A proof that can only succeed proves nothing, so every kind is exercised once
where the claim holds and once where it does not.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from council.domain.findings import State
from council.proofs import EXECUTORS, ProofContext, change_lines, run_proof
from council.domain.schema import PROOF_KINDS

ALLOW = frozenset({"true", "false", "sh", "jq", "python3"})


def ctx(repo: Path, *, diff: str | None = None) -> ProofContext:
    return ProofContext(repo=repo, allow=ALLOW, diff=diff, timeout=10, sandbox=False)


def sandbox_ctx(repo: Path) -> ProofContext:
    return ProofContext(repo=repo, allow=ALLOW, timeout=20, sandbox=True)


def _require_userns() -> None:
    """These proofs need user namespaces. A host without them cannot run the gate.

    No `skipif`: a skipped test is a pass that measured nothing, and this repository
    treats that as a failure. The gate runs these inside the Nix sandbox, where bwrap
    can unshare; a host that cannot is a host that cannot prove the sandbox.
    """
    assert _userns_ok(), (
        "the sandbox proofs need user namespaces (bwrap --unshare-all); this host "
        "cannot run them, so it cannot prove the sandbox"
    )


def _userns_ok() -> bool:
    """Can this environment run the sandbox at all?

    The probe names an executable that exists in the devshell AND in the Nix build
    sandbox. `/bin/true` exists on the host and in no sandbox, so the old probe answered
    "no user namespaces" inside the gate and the three proofs below skipped there -- for
    every gate run since they were written -- while passing on a developer's machine.
    """
    bwrap = shutil.which("bwrap")
    if bwrap is None:
        return False
    probe = sys.executable or shutil.which("sh")
    if probe is None:
        return False
    return subprocess.run(
        [bwrap, "--unshare-all", "--ro-bind", "/", "/", probe, "-c", "pass"],
        capture_output=True,
    ).returncode == 0


def write(repo: Path, name: str, text: str) -> Path:
    path = repo / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


# --- absent -----------------------------------------------------------------

def test_absent_holds_when_the_pattern_is_nowhere(tmp_path: Path) -> None:
    write(tmp_path, "a.py", "x = 1\n")
    outcome = run_proof("absent", {"pattern": "SECRET"}, ctx(tmp_path))
    assert outcome.state is State.PROVEN


def test_absent_fails_and_names_the_line(tmp_path: Path) -> None:
    write(tmp_path, "a.py", "x = 1\nSECRET = 2\n")
    outcome = run_proof("absent", {"pattern": "SECRET"}, ctx(tmp_path))
    assert outcome.state is State.REFUTED
    assert "a.py:2" in outcome.detail


def test_absent_honours_exclude(tmp_path: Path) -> None:
    write(tmp_path, "vendor/x.py", "SECRET\n")
    outcome = run_proof("absent", {"pattern": "SECRET", "exclude": ["vendor/*"]}, ctx(tmp_path))
    assert outcome.state is State.PROVEN


def test_absent_skips_git_and_run_state(tmp_path: Path) -> None:
    write(tmp_path, ".git/objects/x", "SECRET\n")
    write(tmp_path, ".council/runs/1/sample-1.json", "SECRET\n")
    outcome = run_proof("absent", {"pattern": "SECRET"}, ctx(tmp_path))
    assert outcome.state is State.PROVEN


def test_absent_does_not_follow_a_symlink_out_of_the_repository(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside-secret.txt"
    outside.write_text("SECRET\n", encoding="utf-8")
    (tmp_path / "link.txt").symlink_to(outside)
    outcome = run_proof("absent", {"pattern": "SECRET"}, ctx(tmp_path))
    assert outcome.state is State.PROVEN


def test_a_command_with_a_nul_cannot_run(tmp_path: Path) -> None:
    outcome = run_proof("command", {"argv": ["true", "\0"]}, ctx(tmp_path))
    assert outcome.state is State.UNRUNNABLE


def test_a_proof_that_crashes_is_unrunnable(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(params: object, context: object) -> object:
        raise RuntimeError("boom")

    monkeypatch.setitem(EXECUTORS, "absent", boom)
    outcome = run_proof("absent", {"pattern": "x"}, ctx(tmp_path))
    assert outcome.state is State.UNRUNNABLE
    assert "crashed" in outcome.detail


def test_an_invalid_regex_cannot_run(tmp_path: Path) -> None:
    assert run_proof("absent", {"pattern": "("}, ctx(tmp_path)).state is State.UNRUNNABLE


# --- present ----------------------------------------------------------------

def test_present_holds_on_the_expected_line(tmp_path: Path) -> None:
    write(tmp_path, "a.py", "one\ntwo\n")
    outcome = run_proof("present", {"path": "a.py", "line": 2, "text": "two"}, ctx(tmp_path))
    assert outcome.state is State.PROVEN


def test_present_fails_on_another_line_text(tmp_path: Path) -> None:
    write(tmp_path, "a.py", "one\ntwo\n")
    outcome = run_proof("present", {"path": "a.py", "line": 2, "text": "three"}, ctx(tmp_path))
    assert outcome.state is State.REFUTED


def test_present_accepts_a_quote_that_omits_its_indentation(tmp_path: Path) -> None:
    """A diff quote starts at the code, not at the column: indentation is layout."""
    write(tmp_path, "a.py", "def f():\n    return 1\n")
    outcome = run_proof("present", {"path": "a.py", "line": 2, "text": "return 1"},
                        ctx(tmp_path))
    assert outcome.state is State.PROVEN


def test_present_refuses_more_than_indentation(tmp_path: Path) -> None:
    write(tmp_path, "a.py", "def f():\n    return 1\n")
    outcome = run_proof("present", {"path": "a.py", "line": 2, "text": "return 2"},
                        ctx(tmp_path))
    assert outcome.state is State.REFUTED
    assert "return 1" in outcome.detail and "return 2" in outcome.detail


def test_present_cannot_read_a_missing_file(tmp_path: Path) -> None:
    outcome = run_proof("present", {"path": "gone.py", "line": 1, "text": "x"}, ctx(tmp_path))
    assert outcome.state is State.UNRUNNABLE


def test_present_refuses_a_fifo_without_opening_it(tmp_path: Path) -> None:
    os.mkfifo(tmp_path / "pipe")
    outcome = run_proof("present", {"path": "pipe", "line": 1, "text": "x"},
                        ctx(tmp_path))
    assert outcome.state is State.UNRUNNABLE
    assert "regular file" in outcome.detail


def test_present_cannot_read_past_the_end(tmp_path: Path) -> None:
    write(tmp_path, "a.py", "one\n")
    outcome = run_proof("present", {"path": "a.py", "line": 9, "text": "x"}, ctx(tmp_path))
    assert outcome.state is State.UNRUNNABLE


def test_a_path_that_leaves_the_repository_cannot_run(tmp_path: Path) -> None:
    outcome = run_proof("present", {"path": "../../etc/passwd", "line": 1, "text": "x"}, ctx(tmp_path))
    assert outcome.state is State.UNRUNNABLE


# --- command ----------------------------------------------------------------

def test_a_command_that_exits_zero_holds(tmp_path: Path) -> None:
    assert run_proof("command", {"argv": ["true"]}, ctx(tmp_path)).state is State.PROVEN


def test_a_command_that_exits_nonzero_fails(tmp_path: Path) -> None:
    outcome = run_proof("command", {"argv": ["false"]}, ctx(tmp_path))
    assert outcome.state is State.REFUTED


def test_a_nonzero_command_can_be_the_expectation(tmp_path: Path) -> None:
    outcome = run_proof("command", {"argv": ["false"], "expect": {"exit": "nonzero"}}, ctx(tmp_path))
    assert outcome.state is State.PROVEN


def test_an_unlisted_binary_cannot_run(tmp_path: Path) -> None:
    outcome = run_proof("command", {"argv": ["curl", "http://example.invalid"]}, ctx(tmp_path))
    assert outcome.state is State.UNRUNNABLE
    assert "allow" in outcome.detail


def test_a_path_instead_of_a_name_cannot_run(tmp_path: Path) -> None:
    outcome = run_proof("command", {"argv": ["/usr/bin/env", "true"]}, ctx(tmp_path))
    assert outcome.state is State.UNRUNNABLE


def test_a_shell_command_runs_only_when_the_shell_is_allowed(tmp_path: Path) -> None:
    assert run_proof("command", {"argv": ["sh", "-c", "exit 0"]}, ctx(tmp_path)).state is State.PROVEN


NETWORK_PROBE = "import socket; socket.create_connection(('1.1.1.1', 80), 2)"


def test_without_bwrap_a_command_proof_does_not_run(tmp_path: Path,
                                                    monkeypatch: pytest.MonkeyPatch) -> None:
    """No sandbox is not a reason to run unsandboxed: it is a reason to say so."""
    monkeypatch.setattr("council.sandbox.shutil.which", lambda _: None)
    outcome = run_proof("command", {"argv": ["true"]}, sandbox_ctx(tmp_path))
    assert outcome.state is State.UNRUNNABLE
    assert "bwrap" in outcome.detail


def test_the_sandbox_blocks_the_network(tmp_path: Path) -> None:
    _require_userns()
    outcome = run_proof("command",
                        {"argv": ["python3", "-c", NETWORK_PROBE],
                         "expect": {"exit": "nonzero"}},
                        sandbox_ctx(tmp_path))
    assert outcome.state is State.PROVEN, outcome.detail


def test_the_sandbox_discards_writes_to_the_repository(tmp_path: Path) -> None:
    _require_userns()
    """A tool may write; the tree it judges is unchanged when the proof exits."""
    (tmp_path / "a.txt").write_text("x\n", encoding="utf-8")
    outcome = run_proof("command", {"argv": ["sh", "-c", "echo y > a.txt"]},
                        sandbox_ctx(tmp_path))
    assert outcome.state is State.PROVEN, outcome.detail
    assert (tmp_path / "a.txt").read_text(encoding="utf-8") == "x\n"


def test_a_write_outside_the_repository_is_unrunnable(tmp_path: Path) -> None:
    _require_userns()
    outcome = run_proof("command", {"argv": ["sh", "-c", "echo y > /etc/zz-sandbox"]},
                        sandbox_ctx(tmp_path))
    assert outcome.state is State.UNRUNNABLE
    assert "read-only" in outcome.detail
    assert not Path("/etc/zz-sandbox").exists()


# --- json -------------------------------------------------------------------

def test_json_holds_when_the_pointer_equals(tmp_path: Path) -> None:
    write(tmp_path, "d.json", json.dumps({"a": {"b": [1, 2]}}))
    outcome = run_proof("json", {"path": "d.json", "pointer": "/a/b/1", "equals": 2}, ctx(tmp_path))
    assert outcome.state is State.PROVEN


def test_json_fails_when_the_value_differs(tmp_path: Path) -> None:
    write(tmp_path, "d.json", json.dumps({"a": 1}))
    outcome = run_proof("json", {"path": "d.json", "pointer": "/a", "equals": 2}, ctx(tmp_path))
    assert outcome.state is State.REFUTED


def test_json_does_not_let_true_pass_for_one(tmp_path: Path) -> None:
    write(tmp_path, "d.json", json.dumps({"a": True}))
    outcome = run_proof("json", {"path": "d.json", "pointer": "/a", "equals": 1}, ctx(tmp_path))
    assert outcome.state is State.REFUTED


def test_json_cannot_resolve_a_missing_pointer(tmp_path: Path) -> None:
    write(tmp_path, "d.json", json.dumps({"a": 1}))
    outcome = run_proof("json", {"path": "d.json", "pointer": "/b", "equals": 1}, ctx(tmp_path))
    assert outcome.state is State.UNRUNNABLE


def test_json_pointer_rejects_a_negative_index(tmp_path: Path) -> None:
    write(tmp_path, "d.json", json.dumps({"a": [1, 2]}))
    outcome = run_proof("json", {"path": "d.json", "pointer": "/a/-1", "equals": 2},
                        ctx(tmp_path))
    assert outcome.state is State.UNRUNNABLE


def test_json_pointer_rejects_a_leading_zero(tmp_path: Path) -> None:
    write(tmp_path, "d.json", json.dumps({"a": [1, 2]}))
    outcome = run_proof("json", {"path": "d.json", "pointer": "/a/01", "equals": 2},
                        ctx(tmp_path))
    assert outcome.state is State.UNRUNNABLE


def test_every_declared_kind_has_an_executor() -> None:
    assert set(PROOF_KINDS) == set(EXECUTORS)


# --- diff -------------------------------------------------------------------

MULTI_HUNK = """diff --git a/a.py b/a.py
--- a/a.py
+++ b/a.py
@@ -1,3 +1,3 @@
 line1
-line2
+LINE2
 line3
@@ -20,3 +20,4 @@
 line20
+ADDED21
 line21
 line22
"""


def test_change_lines_reads_every_hunk() -> None:
    added, removed = change_lines(MULTI_HUNK)["a.py"]
    assert added == {2, 21}
    assert removed == {2}


def test_a_diff_proof_reads_a_line_in_the_second_hunk(tmp_path: Path) -> None:
    """The v1 parser reset its offsets at each hunk and only saw the last one."""
    outcome = run_proof("diff", {"path": "a.py", "line": 21, "mode": "added"},
                        ctx(tmp_path, diff=MULTI_HUNK))
    assert outcome.state is State.PROVEN


def test_a_diff_proof_reports_a_line_that_was_not_added(tmp_path: Path) -> None:
    outcome = run_proof("diff", {"path": "a.py", "line": 20, "mode": "added"},
                        ctx(tmp_path, diff=MULTI_HUNK))
    assert outcome.state is State.REFUTED


def test_a_removed_line_is_read_from_the_old_file(tmp_path: Path) -> None:
    outcome = run_proof("diff", {"path": "a.py", "line": 2, "mode": "removed"},
                        ctx(tmp_path, diff=MULTI_HUNK))
    assert outcome.state is State.PROVEN


def test_a_diff_proof_without_a_diff_cannot_run(tmp_path: Path) -> None:
    outcome = run_proof("diff", {"path": "a.py", "line": 1, "mode": "added"}, ctx(tmp_path))
    assert outcome.state is State.UNRUNNABLE


# --- dispatch ---------------------------------------------------------------

def test_an_unknown_kind_cannot_run(tmp_path: Path) -> None:
    assert run_proof("vibes", {}, ctx(tmp_path)).state is State.UNRUNNABLE


def test_malformed_params_cannot_run(tmp_path: Path) -> None:
    assert run_proof("present", {"path": "a.py"}, ctx(tmp_path)).state is State.UNRUNNABLE


# --- absent, scoped ---------------------------------------------------------

def test_a_scoped_absence_ignores_a_hit_outside_the_scope(tmp_path: Path) -> None:
    """The module-level claim, not the repository, is what the finding is about."""
    write(tmp_path, "src/a.py", "x = 1\n")
    write(tmp_path, "docs/notes.md", "no lru_cache here either\n")
    outcome = run_proof("absent", {"pattern": "lru_cache", "within": ["src/**"]}, ctx(tmp_path))
    assert outcome.state is State.PROVEN


def test_a_scoped_absence_still_names_a_hit_inside_the_scope(tmp_path: Path) -> None:
    write(tmp_path, "src/a.py", "x = 1\nlru_cache = 2\n")
    write(tmp_path, "docs/notes.md", "nothing\n")
    outcome = run_proof("absent", {"pattern": "lru_cache", "within": ["src/**"]}, ctx(tmp_path))
    assert outcome.state is State.REFUTED
    assert "src/a.py:2" in outcome.detail


def test_a_scope_that_matches_no_file_cannot_prove_an_absence(tmp_path: Path) -> None:
    write(tmp_path, "src/a.py", "x = 1\n")
    outcome = run_proof("absent", {"pattern": "x", "within": ["nowhere/**"]}, ctx(tmp_path))
    assert outcome.state is State.UNRUNNABLE
    assert "nothing was searched" in outcome.detail


def test_a_scope_that_leaves_the_repository_cannot_run(tmp_path: Path) -> None:
    outcome = run_proof("absent", {"pattern": "x", "within": ["../etc/**"]}, ctx(tmp_path))
    assert outcome.state is State.UNRUNNABLE


# --- repro ------------------------------------------------------------------

def test_a_repro_that_fails_proves_the_finding(tmp_path: Path) -> None:
    outcome = run_proof("repro", {"argv": ["sh", "-c", "exit 1"]}, ctx(tmp_path))
    assert outcome.state is State.PROVEN


def test_a_repro_that_succeeds_refutes_the_finding(tmp_path: Path) -> None:
    outcome = run_proof("repro", {"argv": ["true"]}, ctx(tmp_path))
    assert outcome.state is State.REFUTED
    assert "did not reproduce" in outcome.detail


def test_a_repro_must_show_the_claimed_failure(tmp_path: Path) -> None:
    outcome = run_proof("repro", {"argv": ["sh", "-c", "echo other >&2; exit 1"],
                                  "contains": "boom"}, ctx(tmp_path))
    assert outcome.state is State.REFUTED
    assert "not the failure" in outcome.detail


def test_a_repro_that_shows_the_claimed_failure_proves(tmp_path: Path) -> None:
    outcome = run_proof("repro", {"argv": ["sh", "-c", "echo boom; exit 2"],
                                  "contains": "boom"}, ctx(tmp_path))
    assert outcome.state is State.PROVEN


def test_a_repro_naming_an_unlisted_binary_cannot_run(tmp_path: Path) -> None:
    outcome = run_proof("repro", {"argv": ["curl", "http://example.invalid"]}, ctx(tmp_path))
    assert outcome.state is State.UNRUNNABLE
    assert "allow" in outcome.detail


def test_without_bwrap_a_repro_does_not_run(tmp_path: Path,
                                           monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("council.sandbox.shutil.which", lambda _: None)
    outcome = run_proof("repro", {"argv": ["true"]}, sandbox_ctx(tmp_path))
    assert outcome.state is State.UNRUNNABLE
    assert "bwrap" in outcome.detail


# --- proof infrastructure and stale locations --------------------------------

def test_present_reports_a_stale_line_instead_of_refuting(tmp_path: Path) -> None:
    write(tmp_path, "a.py", "one\ntwo\n")
    outcome = run_proof("present", {"path": "a.py", "line": 1, "text": "two"}, ctx(tmp_path))
    assert outcome.state is State.UNRUNNABLE
    assert "line 2" in outcome.detail


def test_a_repro_with_a_missing_module_is_unrunnable(tmp_path: Path) -> None:
    outcome = run_proof(
        "repro",
        {"argv": ["python3", "-c", "import council_missing_dependency"],
         "contains": "claimed failure"},
        ctx(tmp_path),
    )
    assert outcome.state is State.UNRUNNABLE
    assert "dependency" in outcome.detail


def test_a_command_with_a_missing_module_is_unrunnable_even_when_nonzero(
        tmp_path: Path) -> None:
    outcome = run_proof(
        "command",
        {"argv": ["python3", "-c", "import council_missing_dependency"],
         "expect": {"exit": "nonzero"}},
        ctx(tmp_path),
    )
    assert outcome.state is State.UNRUNNABLE
    assert "dependency" in outcome.detail


def test_python_is_normalised_to_python3_when_allowed(tmp_path: Path) -> None:
    outcome = run_proof("command", {"argv": ["python", "-c", "pass"]}, ctx(tmp_path))
    assert outcome.state is State.PROVEN


def test_a_message_mentioning_a_missing_module_is_not_infrastructure_failure(
        tmp_path: Path) -> None:
    outcome = run_proof(
        "repro",
        {"argv": ["sh", "-c", "echo 'check failed: No module named'; exit 1"],
         "contains": "claimed failure"},
        ctx(tmp_path),
    )
    assert outcome.state is State.REFUTED


def test_a_test_name_mentioning_module_not_found_is_not_infrastructure(
        tmp_path: Path) -> None:
    outcome = run_proof(
        "repro",
        {"argv": ["sh", "-c", "echo 'FAILED test_errors.py::test_handles_ModuleNotFoundError - AssertionError'; exit 1"],
         "contains": "claimed failure"},
        ctx(tmp_path),
    )
    assert outcome.state is State.REFUTED


def test_a_pytest_prefixed_module_error_is_unrunnable(tmp_path: Path) -> None:
    outcome = run_proof(
        "repro",
        {"argv": ["sh", "-c", "printf 'E   ModuleNotFoundError: No module named x\\n'; exit 1"],
         "contains": "claimed failure"},
        ctx(tmp_path),
    )
    assert outcome.state is State.UNRUNNABLE


def test_a_repro_that_matches_a_missing_module_is_evidence(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import council.proofs as proofs

    message = "ModuleNotFoundError: No module named 'reviewed_package.required'"
    monkeypatch.setattr(proofs, "_attempt",
                        lambda argv, context: proofs._Ran(1, message, "", message))
    outcome = proofs.proof_repro({"argv": ["python3", "-m", "reviewed_package"],
                                 "contains": message}, ctx(tmp_path))
    assert outcome.state is State.PROVEN


def test_a_repro_without_contains_does_not_treat_a_missing_module_as_proof(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import council.proofs as proofs

    monkeypatch.setattr(
        proofs, "_attempt",
        lambda argv, context: proofs._Ran(
            1, "ModuleNotFoundError: No module named 'reviewed_package'",
            "", "ModuleNotFoundError: No module named 'reviewed_package'"))
    outcome = proofs.proof_repro({"argv": ["python3", "-m", "reviewed_package"]},
                                 ctx(tmp_path))
    assert outcome.state is State.UNRUNNABLE


def test_a_dotted_module_without_its_parent_is_unrunnable(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import council.proofs as proofs

    message = ("/usr/bin/python3: Error while finding module specification for "
               "'alpha.beta' (ModuleNotFoundError: No module named 'alpha')")
    monkeypatch.setattr(proofs, "_attempt",
                        lambda argv, context: proofs._Ran(1, message, "", message))
    outcome = proofs.proof_repro({"argv": ["python3", "-m", "alpha.beta"]},
                                 ctx(tmp_path))
    assert outcome.state is State.UNRUNNABLE


def test_a_test_failure_that_quotes_the_exception_is_not_a_missing_dependency(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import council.proofs as proofs

    quoted = ("AssertionError: the guard raised ModuleNotFoundError: "
              "No module named 'reviewed_package' but it should not have")
    # The quote is on stdout; stderr carries only pytest's own summary.
    monkeypatch.setattr(
        proofs, "_attempt",
        lambda argv, context: proofs._Ran(
            1, quoted, quoted,
            "FAILED tests/test_guard.py::test_the_guard - AssertionError"))
    outcome = proofs.proof_repro({"argv": ["python3", "tests/test_guard.py"]},
                                 ctx(tmp_path))
    assert outcome.state is State.PROVEN


def test_a_module_bug_is_not_a_missing_dependency(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """`-m` reports the same clause when the package itself raises."""
    import council.proofs as proofs

    message = ("/usr/bin/python3: Error while finding module specification for "
               "'reviewed_package.cli' (AttributeError: module 'reviewed_package' "
               "has no attribute 'cli')")
    monkeypatch.setattr(proofs, "_attempt",
                        lambda argv, context: proofs._Ran(1, message, "", message))
    outcome = proofs.proof_repro({"argv": ["python3", "-m", "reviewed_package.cli"]},
                                 ctx(tmp_path))
    assert outcome.state is State.PROVEN


def test_stdout_without_a_newline_cannot_hide_a_dependency_diagnostic(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import council.proofs as proofs

    diagnostic = "/usr/bin/python3: No module named 'reviewed_package'"
    monkeypatch.setattr(
        proofs, "_attempt",
        lambda argv, context: proofs._Ran(
            1, "partial output" + diagnostic, "partial output", diagnostic))
    outcome = proofs.proof_repro({"argv": ["python3", "-m", "reviewed_package"]},
                                 ctx(tmp_path))
    assert outcome.state is State.UNRUNNABLE


def test_a_progress_message_cannot_prove_a_run_that_lacked_a_dependency(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A match in stdout is not evidence when the run died on an import."""
    import council.proofs as proofs

    monkeypatch.setattr(
        proofs, "_attempt",
        lambda argv, context: proofs._Ran(
            1, "starting...\n", "starting...\n",
            "ModuleNotFoundError: No module named 'reviewed_package'"))
    outcome = proofs.proof_repro({"argv": ["python3", "-m", "reviewed_package"],
                                 "contains": "starting..."}, ctx(tmp_path))
    assert outcome.state is State.UNRUNNABLE


def test_the_explanation_text_is_never_matched_against_contains(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """`contains` describes the command's output, not Council's own prose."""
    import council.proofs as proofs

    message = "ModuleNotFoundError: No module named 'example'"
    monkeypatch.setattr(
        proofs, "_attempt",
        lambda argv, context: proofs._Ran(1, message, "", message))
    outcome = proofs.proof_repro(
        {"argv": ["python3"], "contains": "the proof could not import a dependency"},
        ctx(tmp_path))
    assert outcome.state is State.UNRUNNABLE
