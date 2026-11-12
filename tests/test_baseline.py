"""Baseline policy: accepted risks are explicit, expiring and never evidence."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

import council.cli as cli
from council.baseline import (
    BaselineError,
    from_run,
    load,
    load_at,
    run_fingerprints,
    write,
)
from council.domain.baseline import (
    Baseline,
    BaselineEntry,
    BaselineError as DomainBaselineError,
    apply_baseline,
    entry_from_finding,
    fingerprint,
    from_findings,
    parse,
    render,
)
from council.findings import Finding, State
from council.verdict import Result, Verdict

CREATED = date(2026, 1, 1)
EXPIRES = date(2026, 4, 1)
TODAY = date(2026, 2, 1)
PROOF = '[["present",{"line":2,"path":"a.py","text":"two"}]]'


def finding(*, state: State = State.PROVEN, dimension: str = "correctness",
            severity: str = "high", location: str = "a.py:2",
            claim: str = "It is wrong.", proof: str = PROOF,
            identifier: str = "F-01") -> Finding:
    return Finding(identifier, dimension, severity, state, location, claim, "detail", proof)


def entry(item: Finding | None = None, *, expires: date = EXPIRES) -> BaselineEntry:
    item = item or finding()
    return entry_from_finding(item, owner="team", reason="accepted for now",
                              created=CREATED, expires=expires)


def result(*findings: Finding, verdict: Verdict = Verdict.FAIL,
           reason: str = "a finding") -> Result:
    return Result(verdict, reason, tuple(findings))


def test_a_matching_proven_finding_is_suppressed_after_the_verdict() -> None:
    item = finding()
    baseline = Baseline((entry(item),))

    gate = apply_baseline(result(item), baseline, today=TODAY)

    assert gate.verdict is Verdict.PASS
    assert gate.exit_code == 0
    assert gate.suppressed == ("F-01",)
    assert "baselined" in gate.reason
    # The evidence result is untouched.
    assert result(item).verdict is Verdict.FAIL


def test_a_new_finding_is_not_suppressed() -> None:
    baseline = Baseline((entry(finding(claim="An old claim.")),))
    gate = apply_baseline(result(finding(claim="A new claim.")), baseline, today=TODAY)
    assert gate.verdict is Verdict.FAIL
    assert gate.suppressed == ()
    assert "stale" in gate.reason


def test_strict_mode_fails_a_stale_baseline_even_when_evidence_passes() -> None:
    baseline = Baseline((entry(finding(claim="An old claim.")),))
    gate = apply_baseline(result(verdict=Verdict.PASS, reason="clean"),
                          baseline, today=TODAY, strict=True)
    assert gate.verdict is Verdict.FAIL
    assert "strict" in gate.reason


def test_an_unsettled_finding_cannot_be_suppressed() -> None:
    item = finding(state=State.UNSETTLED)
    gate = apply_baseline(result(item, verdict=Verdict.INCOMPLETE,
                                 reason="missing evidence"),
                          Baseline((entry(item),)), today=TODAY)
    assert gate.verdict is Verdict.INCOMPLETE
    assert gate.exit_code == 2
    assert gate.suppressed == ()


def test_an_unrunnable_finding_cannot_be_suppressed() -> None:
    item = finding(state=State.UNRUNNABLE)
    gate = apply_baseline(result(item, verdict=Verdict.INCOMPLETE,
                                 reason="a proof could not run"),
                          Baseline((entry(item),)), today=TODAY)
    assert gate.verdict is Verdict.INCOMPLETE
    assert gate.suppressed == ()


def test_an_expired_entry_does_not_suppress() -> None:
    item = finding()
    gate = apply_baseline(result(item), Baseline((entry(item, expires=date(2026, 1, 31)),)),
                          today=TODAY)
    assert gate.verdict is Verdict.FAIL
    assert gate.suppressed == ()
    assert gate.expired


def test_a_missing_sample_is_not_turned_into_a_pass() -> None:
    item = finding()
    evidence = Result(Verdict.INCOMPLETE, "sample 2 returned nothing", (item,))
    gate = apply_baseline(evidence, Baseline((entry(item),)), today=TODAY)
    assert gate.verdict is Verdict.INCOMPLETE
    assert gate.exit_code == 2


def test_a_failing_verdict_with_missing_evidence_cannot_become_a_pass() -> None:
    item = finding()
    evidence = Result(Verdict.FAIL, "a finding; sample 2 returned nothing", (item,))
    gate = apply_baseline(evidence, Baseline((entry(item),)), today=TODAY,
                          missing_evidence=True)
    assert gate.verdict is Verdict.INCOMPLETE
    assert gate.exit_code == 2
    assert "missing evidence" in gate.reason


def test_a_baselined_nonblocking_finding_is_not_suppressed() -> None:
    item = finding(dimension="readability", severity="low")
    gate = apply_baseline(result(item, verdict=Verdict.PASS, reason="no blocking findings"),
                          Baseline((entry(item),)), today=TODAY)
    assert gate.verdict is Verdict.PASS
    assert gate.suppressed == ()
    assert gate.stale


def test_only_proven_blocking_findings_enter_a_baseline() -> None:
    clean = finding(identifier="F-01")
    low = finding(identifier="F-02", dimension="readability", severity="low")
    open_ = finding(identifier="F-03", state=State.UNSETTLED)
    baseline = from_findings((clean, low, open_), owner="team", reason="why",
                             created=CREATED, expires=EXPIRES)
    assert [item.fingerprint for item in baseline.entries] == [fingerprint(clean)]


def test_a_severity_escalation_is_not_covered_by_an_old_baseline() -> None:
    old = finding(severity="high")
    baseline = Baseline((entry(old),))
    gate = apply_baseline(result(finding(severity="critical")), baseline, today=TODAY)
    assert gate.verdict is Verdict.FAIL
    assert gate.suppressed == ()


def test_whitespace_does_not_change_the_claimed_identity() -> None:
    left = finding(claim="It  is\nwrong.")
    right = finding(claim="It is wrong.")
    assert fingerprint(left) == fingerprint(right)


def test_a_changed_proof_changes_the_fingerprint() -> None:
    left = finding(proof=PROOF)
    right = finding(proof='[["present",{"line":3,"path":"a.py","text":"three"}]]')
    assert fingerprint(left) != fingerprint(right)


def test_parse_and_render_round_trip() -> None:
    baseline = Baseline((entry(),))
    assert parse(render(baseline)) == baseline


@pytest.mark.parametrize("body", [
    "{",
    '{"version":2,"entries":[]}',
    '{"version":1,"entries":[]} trailing',
    '{"version":1,"entries":[],"unknown":1}',
    '{"version":1,"entries":[{}]}',
])
def test_malformed_baselines_are_refused(body: str) -> None:
    with pytest.raises(DomainBaselineError):
        parse(body)


def test_duplicate_fingerprints_are_refused() -> None:
    item = entry()
    payload = json.loads(render(Baseline((item,))))
    payload["entries"].append(payload["entries"][0])
    with pytest.raises(DomainBaselineError, match="duplicate"):
        parse(json.dumps(payload))


def test_a_tampered_fingerprint_is_refused() -> None:
    payload = json.loads(render(Baseline((entry(),))))
    payload["entries"][0]["claim"] = "A different claim."
    with pytest.raises(DomainBaselineError, match="fingerprint"):
        parse(json.dumps(payload))


def test_an_entry_requires_an_owner_and_reason() -> None:
    item = finding()
    with pytest.raises(DomainBaselineError, match="owner"):
        entry_from_finding(item, owner="", reason="why", created=CREATED, expires=EXPIRES)


def test_an_entry_cannot_expire_before_it_was_created() -> None:
    with pytest.raises(DomainBaselineError, match="expires"):
        entry_from_finding(finding(), owner="team", reason="why",
                           created=EXPIRES, expires=CREATED)


# ---- adapter -------------------------------------------------------------

def test_a_symlinked_baseline_is_refused(tmp_path: Path) -> None:
    target = tmp_path / "real.json"
    target.write_text(render(Baseline((entry(),))), encoding="utf-8")
    link = tmp_path / "link.json"
    link.symlink_to(target)
    with pytest.raises(BaselineError, match="symlink"):
        load(link)


def test_a_missing_baseline_is_refused(tmp_path: Path) -> None:
    with pytest.raises(BaselineError, match="no baseline"):
        load(tmp_path / "absent.json")


def test_write_is_atomic_and_canonical(tmp_path: Path) -> None:
    path = tmp_path / "baseline.json"
    write(path, Baseline((entry(),)))
    assert path.read_text(encoding="utf-8") == render(Baseline((entry(),)))
    assert path.read_text(encoding="utf-8").endswith("\n")


def test_a_fifo_baseline_is_refused(tmp_path: Path) -> None:
    if not hasattr(__import__("os"), "mkfifo"):
        pytest.skip("no FIFO on this host")
    path = tmp_path / "fifo.json"
    __import__("os").mkfifo(path)
    with pytest.raises(BaselineError, match="regular file"):
        load(path)


def _git(repo: Path, *args: str) -> None:
    import subprocess
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


def test_load_at_reads_the_base_revision_not_the_worktree(tmp_path: Path) -> None:
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "test@example.invalid")
    _git(tmp_path, "config", "user.name", "test")
    baseline = render(Baseline((entry(),)))
    (tmp_path / "baseline.json").write_text(baseline, encoding="utf-8")
    _git(tmp_path, "add", "baseline.json")
    _git(tmp_path, "commit", "-qm", "baseline")
    base = __import__("subprocess").run(
        ["git", "rev-parse", "HEAD"], cwd=tmp_path, check=True,
        capture_output=True, text=True).stdout.strip()
    (tmp_path / "baseline.json").write_text("{}", encoding="utf-8")
    assert load_at(tmp_path, base, "baseline.json") == Baseline((entry(),))


def test_load_at_refuses_a_non_utf8_baseline(tmp_path: Path) -> None:
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "test@example.invalid")
    _git(tmp_path, "config", "user.name", "test")
    (tmp_path / "baseline.json").write_bytes(b"\xff\xfe")
    _git(tmp_path, "add", "baseline.json")
    _git(tmp_path, "commit", "-qm", "bad baseline")
    with pytest.raises(BaselineError, match="UTF-8"):
        load_at(tmp_path, "HEAD", "baseline.json")


def test_load_at_refuses_a_path_that_escapes(tmp_path: Path) -> None:
    with pytest.raises(BaselineError, match="invalid baseline path"):
        load_at(tmp_path, "HEAD", "../baseline.json")


def test_a_run_can_create_and_prune_a_baseline(tmp_path: Path) -> None:
    run = tmp_path / "run"
    run.mkdir()
    item = finding(proof=PROOF)
    (run / "verdict.json").write_text(json.dumps({
        "findings": [{
            "id": "F-01", "dimension": "correctness", "severity": "high",
            "state": "proven", "location": "a.py:2",
            "claim": "It is wrong.", "proof": item.proof,
        }],
    }), encoding="utf-8")
    baseline = from_run(run, owner="team", reason="why", created=CREATED,
                        expires=EXPIRES)
    assert run_fingerprints(run) == {entry(item).fingerprint}
    assert len(baseline.entries) == 1


def test_an_incomplete_run_cannot_seed_a_baseline(tmp_path: Path) -> None:
    run = tmp_path / "incomplete"
    run.mkdir()
    item = finding()
    (run / "verdict.json").write_text(json.dumps({
        "verdict": "incomplete",
        "findings": [{
            "id": "F-01", "dimension": "correctness", "severity": "high",
            "state": "proven", "location": "a.py:2",
            "claim": "It is wrong.", "proof": item.proof,
        }],
        "samples": [{"index": 1, "ok": False}],
    }), encoding="utf-8")
    with pytest.raises(BaselineError, match="incomplete"):
        from_run(run, owner="team", reason="why", created=CREATED, expires=EXPIRES)


def test_the_cli_creates_a_baseline_from_a_run(tmp_path: Path,
                                               capsys: pytest.CaptureFixture[str]) -> None:
    run = tmp_path / "run"
    run.mkdir()
    item = finding()
    (run / "verdict.json").write_text(json.dumps({
        "findings": [{
            "id": "F-01", "dimension": "correctness", "severity": "high",
            "state": "proven", "location": "a.py:2",
            "claim": "It is wrong.", "proof": item.proof,
        }],
    }), encoding="utf-8")
    out = tmp_path / "baseline.json"
    code = cli.main(["baseline", "create", "--from", str(run), "--out", str(out),
                     "--owner", "team", "--reason", "accepted"])
    assert code == 0
    assert "wrote" in capsys.readouterr().out
    assert len(parse(out.read_text(encoding="utf-8")).entries) == 1


def test_the_cli_prunes_only_stale_entries(tmp_path: Path) -> None:
    run = tmp_path / "run"
    run.mkdir()
    current = finding(proof=PROOF)
    stale = finding(proof='[["present",{"path":"a.py","line":9,"text":"nine"}]]',
                    claim="An old issue.")
    (run / "verdict.json").write_text(json.dumps({
        "findings": [{
            "id": "F-01", "dimension": "correctness", "severity": "high",
            "state": "proven", "location": "a.py:2",
            "claim": "It is wrong.", "proof": current.proof,
        }],
    }), encoding="utf-8")
    path = tmp_path / "baseline.json"
    write(path, Baseline((entry(current), entry(stale))))
    code = cli.main(["baseline", "prune", "--baseline", str(path),
                     "--from", str(run), "--write"])
    assert code == 0
    remaining = parse(path.read_text(encoding="utf-8"))
    assert [item.fingerprint for item in remaining.entries] == [entry(current).fingerprint]
