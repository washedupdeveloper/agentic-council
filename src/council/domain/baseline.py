"""Pure baseline policy: accepted risks are a gate, not a verdict.

A baseline never changes a finding's state. It can only suppress a `PROVEN`
blocking finding whose fingerprint was deliberately accepted in a committed
file. `UNRUNNABLE` and `UNSETTLED` evidence is never suppressed: a waiver cannot
turn missing evidence into a pass.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date

from ..findings import SEVERITIES, Finding, State
from ..verdict import Result, Verdict, judge
from ..verdict import exit_code as verdict_exit_code

BASELINE_VERSION = 1


class BaselineError(ValueError):
    """The baseline file does not say something this tool will accept."""


@dataclass(frozen=True, slots=True)
class BaselineEntry:
    """One explicitly accepted risk."""

    fingerprint: str
    dimension: str
    severity: str
    file: str
    line: int
    claim: str
    proof: str
    owner: str
    reason: str
    created: date
    expires: date

    def __post_init__(self) -> None:
        if not self.fingerprint or len(self.fingerprint) != 64:
            raise BaselineError("a baseline entry needs a 64-character fingerprint")
        try:
            int(self.fingerprint, 16)
        except ValueError as exc:
            raise BaselineError("a baseline fingerprint must be hexadecimal") from exc
        if not self.dimension or not self.severity or not self.file or not self.claim:
            raise BaselineError(
                "a baseline entry needs a dimension, severity, file and claim")
        if self.severity not in SEVERITIES:
            raise BaselineError(f"unknown baseline severity {self.severity!r}")
        if self.line < 1:
            raise BaselineError("a baseline entry needs a positive line")
        if self.owner.strip() == "" or self.reason.strip() == "":
            raise BaselineError("a baseline entry needs an owner and a reason")
        if self.expires < self.created:
            raise BaselineError("a baseline entry expires before it was created")
        expected = fingerprint_for(self.dimension, self.severity, self.file,
                                   self.claim, self.proof)
        if expected != self.fingerprint:
            raise BaselineError(
                "baseline fingerprint does not match its dimension/severity/file/claim/proof")


@dataclass(frozen=True, slots=True)
class Baseline:
    """The accepted risks, ordered by fingerprint for deterministic output."""

    entries: tuple[BaselineEntry, ...] = ()

    def by_fingerprint(self) -> dict[str, BaselineEntry]:
        return {entry.fingerprint: entry for entry in self.entries}


@dataclass(frozen=True, slots=True)
class GateResult:
    """The evidence verdict after explicit, non-evidence suppression."""

    verdict: Verdict
    reason: str
    suppressed: tuple[str, ...] = ()
    expired: tuple[str, ...] = ()
    stale: tuple[str, ...] = ()
    entries: int = 0

    @property
    def exit_code(self) -> int:
        return verdict_exit_code(self.verdict)


def normalize_claim(claim: str) -> str:
    """Whitespace is not part of a claim's identity."""
    return " ".join(claim.split())


def fingerprint_for(dimension: str, severity: str, file: str, claim: str, proof: str) -> str:
    payload = json.dumps([dimension, severity, file, normalize_claim(claim), proof],
                         separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def fingerprint(finding: Finding) -> str:
    return fingerprint_for(finding.dimension, finding.severity,
                           finding.file, finding.claim, finding.proof)


def entry_from_finding(finding: Finding, *, owner: str, reason: str,
                       created: date, expires: date) -> BaselineEntry:
    """Snapshot one proven blocking finding as an accepted risk."""
    return BaselineEntry(
        fingerprint=fingerprint(finding),
        dimension=finding.dimension,
        severity=finding.severity,
        file=finding.file,
        line=finding.line,
        claim=finding.claim,
        proof=finding.proof,
        owner=owner,
        reason=reason,
        created=created,
        expires=expires,
    )


def from_findings(findings: Iterable[Finding], *, owner: str, reason: str,
                  created: date, expires: date) -> Baseline:
    """Only proven blocking findings belong in a baseline."""
    entries: dict[str, BaselineEntry] = {}
    for finding in findings:
        if finding.state is not State.PROVEN or not finding.blocks:
            continue
        entry = entry_from_finding(finding, owner=owner, reason=reason,
                                   created=created, expires=expires)
        entries[entry.fingerprint] = entry
    return Baseline(tuple(sorted(entries.values(), key=lambda item: item.fingerprint)))


def stale_fingerprints(baseline: Baseline, present: Iterable[str]) -> tuple[str, ...]:
    """Baseline entries whose finding is no longer present, sorted."""
    seen = set(present)
    return tuple(sorted(entry.fingerprint for entry in baseline.entries
                        if entry.fingerprint not in seen))


def apply_baseline(result: Result, baseline: Baseline, *, today: date,
                   strict: bool = False, missing_evidence: bool = False) -> GateResult:
    """Suppress only unexpired, proven blocking findings.

    The original `Result` is never mutated. If the evidence already fails, the
    remaining findings are judged afresh; if it is `INCOMPLETE` because a sample
    or unit was missing, that fact survives: a baseline cannot manufacture
    evidence.
    """
    entries = baseline.by_fingerprint()
    suppressed: list[Finding] = []
    expired: list[str] = []
    present: set[str] = set()

    for finding in result.findings:
        if finding.state is not State.PROVEN or not finding.blocks:
            continue
        key = fingerprint(finding)
        present.add(key)
        entry = entries.get(key)
        if entry is None:
            continue
        if today > entry.expires:
            expired.append(key)
        else:
            suppressed.append(finding)

    stale = stale_fingerprints(baseline, present)
    if not suppressed and not expired:
        reason = result.reason
        if stale:
            reason = f"{reason}; {len(stale)} stale baseline entry/entries"
        verdict = result.verdict
        if strict and stale:
            verdict = Verdict.FAIL
            reason = f"baseline strict: stale entries must be pruned; {reason}"
        return GateResult(verdict, reason, stale=stale,
                         entries=len(entries))

    if result.verdict is Verdict.FAIL and suppressed:
        remaining = tuple(item for item in result.findings if item not in suppressed)
        fresh = judge(remaining)
        if fresh.verdict is Verdict.PASS and missing_evidence:
            verdict = Verdict.INCOMPLETE
            reason = (f"no new blocking findings; {len(suppressed)} baselined; "
                      f"missing evidence remains; {result.reason}")
        elif fresh.verdict is Verdict.PASS:
            verdict = Verdict.PASS
            reason = f"no new blocking findings; {len(suppressed)} baselined"
        else:
            verdict = fresh.verdict
            reason = f"{fresh.reason}; {len(suppressed)} baselined"
    else:
        # PASS cannot contain a proven blocking finding, and INCOMPLETE already
        # means missing evidence; neither may be changed by a baseline.
        verdict = result.verdict
        reason = result.reason
        if suppressed:
            reason = f"{reason}; {len(suppressed)} baselined"

    if expired:
        reason = f"{reason}; {len(expired)} expired baseline entry/entries"
    if stale:
        reason = f"{reason}; {len(stale)} stale baseline entry/entries"
    if strict and (expired or stale):
        verdict = Verdict.FAIL
        reason = f"baseline strict: expired or stale entries must be resolved; {reason}"

    return GateResult(verdict, reason,
                      suppressed=tuple(item.id for item in suppressed),
                      expired=tuple(sorted(expired)), stale=stale,
                      entries=len(entries))


def parse(text: str) -> Baseline:
    """Parse the committed baseline format. Unknown keys are refused."""
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as exc:
        raise BaselineError(f"baseline is not valid JSON: {exc}") from exc
    if not isinstance(raw, dict):
        raise BaselineError("baseline must be a JSON object")
    unknown = set(raw) - {"version", "entries"}
    if unknown:
        raise BaselineError(f"unknown baseline key(s): {', '.join(sorted(unknown))}")
    version = raw.get("version")
    if version != BASELINE_VERSION:
        raise BaselineError(f"baseline version must be {BASELINE_VERSION}")
    entries_raw = raw.get("entries")
    if not isinstance(entries_raw, list):
        raise BaselineError("baseline entries must be a list")

    entries: list[BaselineEntry] = []
    seen: set[str] = set()
    required = {"fingerprint", "dimension", "severity", "file", "line", "claim", "proof",
                "owner", "reason", "created", "expires"}
    for index, item in enumerate(entries_raw, start=1):
        if not isinstance(item, dict):
            raise BaselineError(f"baseline entry {index} must be an object")
        unknown = set(item) - required
        if unknown:
            raise BaselineError(
                f"baseline entry {index} has unknown key(s): {', '.join(sorted(unknown))}")
        missing = required - set(item)
        if missing:
            raise BaselineError(
                f"baseline entry {index} is missing: {', '.join(sorted(missing))}")
        for key in required - {"line", "created", "expires"}:
            if not isinstance(item[key], str) or not item[key]:
                raise BaselineError(f"baseline entry {index}.{key} must be a non-empty string")
        line_raw = item["line"]
        if isinstance(line_raw, bool) or not isinstance(line_raw, int) or line_raw < 1:
            raise BaselineError(f"baseline entry {index}.line must be a positive integer")
        if not isinstance(item["created"], str) or not isinstance(item["expires"], str):
            raise BaselineError(f"baseline entry {index} dates must be ISO strings")
        try:
            created = date.fromisoformat(item["created"])
            expires = date.fromisoformat(item["expires"])
        except ValueError as exc:
            raise BaselineError(f"baseline entry {index} has an invalid date") from exc
        try:
            entry = BaselineEntry(
                fingerprint=item["fingerprint"],
                dimension=item["dimension"],
                severity=item["severity"],
                file=item["file"],
                line=line_raw,
                claim=item["claim"],
                proof=item["proof"],
                owner=item["owner"],
                reason=item["reason"],
                created=created,
                expires=expires,
            )
        except (TypeError, ValueError) as exc:
            raise BaselineError(f"baseline entry {index} is invalid: {exc}") from exc
        if entry.fingerprint in seen:
            raise BaselineError(f"duplicate baseline fingerprint {entry.fingerprint}")
        seen.add(entry.fingerprint)
        entries.append(entry)
    return Baseline(tuple(sorted(entries, key=lambda entry: entry.fingerprint)))


def render(baseline: Baseline) -> str:
    """The canonical committed form: stable order, one newline."""
    payload = {
        "version": BASELINE_VERSION,
        "entries": [
            {
                "fingerprint": entry.fingerprint,
                "dimension": entry.dimension,
                "severity": entry.severity,
                "file": entry.file,
                "line": entry.line,
                "claim": entry.claim,
                "proof": entry.proof,
                "owner": entry.owner,
                "reason": entry.reason,
                "created": entry.created.isoformat(),
                "expires": entry.expires.isoformat(),
            }
            for entry in baseline.entries
        ],
    }
    return json.dumps(payload, indent=2, sort_keys=False) + "\n"
