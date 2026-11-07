"""Each proof kind, in both directions, plus what cannot run.

A proof that can only succeed proves nothing, so every kind is exercised once
where the claim holds and once where it does not.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from council.findings import State
from council.proofs import EXECUTORS, ProofContext, change_lines, run_proof
from council.schema import PROOF_KINDS

ALLOW = frozenset({"true", "false", "sh", "jq", "python3"})


def ctx(repo: Path, *, diff: str | None = None) -> ProofContext:
    return ProofContext(repo=repo, allow=ALLOW, diff=diff, timeout=10, sandbox=False)


def sandbox_ctx(repo: Path) -> ProofContext:
    return ProofContext(repo=repo, allow=ALLOW, timeout=20, sandbox=True)


def _userns_ok() -> bool:
    bwrap = shutil.which("bwrap")
    if bwrap is None:
        return False
    return subprocess.run([bwrap, "--unshare-all", "--ro-bind", "/", "/", "/bin/true"],
                          capture_output=True).returncode == 0


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


def test_present_cannot_read_a_missing_file(tmp_path: Path) -> None:
    outcome = run_proof("present", {"path": "gone.py", "line": 1, "text": "x"}, ctx(tmp_path))
    assert outcome.state is State.UNRUNNABLE


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


@pytest.mark.skipif(not _userns_ok(), reason="user namespaces are unavailable here")
def test_the_sandbox_blocks_the_network(tmp_path: Path) -> None:
    outcome = run_proof("command",
                        {"argv": ["python3", "-c", NETWORK_PROBE],
                         "expect": {"exit": "nonzero"}},
                        sandbox_ctx(tmp_path))
    assert outcome.state is State.PROVEN, outcome.detail


@pytest.mark.skipif(not _userns_ok(), reason="user namespaces are unavailable here")
def test_the_sandbox_discards_writes_to_the_repository(tmp_path: Path) -> None:
    """A tool may write; the tree it judges is unchanged when the proof exits."""
    (tmp_path / "a.txt").write_text("x\n", encoding="utf-8")
    outcome = run_proof("command", {"argv": ["sh", "-c", "echo y > a.txt"]},
                        sandbox_ctx(tmp_path))
    assert outcome.state is State.PROVEN, outcome.detail
    assert (tmp_path / "a.txt").read_text(encoding="utf-8") == "x\n"


@pytest.mark.skipif(not _userns_ok(), reason="user namespaces are unavailable here")
def test_a_write_outside_the_repository_is_unrunnable(tmp_path: Path) -> None:
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


# --- http / dom -------------------------------------------------------------

def test_an_unreachable_url_cannot_run(tmp_path: Path) -> None:
    outcome = run_proof("http", {"url": "http://127.0.0.1:1/", "expect_status": 200}, ctx(tmp_path))
    assert outcome.state is State.UNRUNNABLE


def test_dom_is_not_a_proof_kind(tmp_path: Path) -> None:
    """A kind the tool cannot run is not offered: DOM claims cite a `command` proof."""
    outcome = run_proof("dom", {"selector": "#x"}, ctx(tmp_path))
    assert outcome.state is State.UNRUNNABLE
    assert "not a proof kind" in outcome.detail


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