# Baselines: accepted risks without hiding evidence

A baseline is a committed list of **proven blocking findings** that a team has
explicitly accepted. It is applied *after* the evidence verdict. It cannot
change a finding's state, cannot suppress missing evidence, and cannot make a
review look cleaner than the run that produced it. SARIF contains only the
findings that still block; the full evidence remains in `verdict.json`.

## The two results

`verdict.json` now carries both:

- `evidence_verdict` — what the findings and proofs settled, unchanged;
- `verdict` — the gate after an explicit baseline policy.

If the evidence is `INCOMPLETE` because a sample, unit or proof was missing, the
gate is `INCOMPLETE` regardless of the baseline. `UNRUNNABLE` and `UNSETTLED`
findings are never suppressible.

## Create a baseline

A baseline is built from a **kept** run. By default a review is ephemeral, so
keep the evidence first:

```sh
council review --no-ephemeral --run-id before
council baseline create \
  --from .council/runs/before \
  --out council-baseline.json \
  --owner "platform-team" \
  --reason "Legacy finding accepted until the Q2 rewrite" \
  --days 90
```

Only `PROVEN` **blocking** findings enter the file. Non-blocking findings are
not accepted risks; they are already outside the gate. A run with
`verdict: incomplete`, a failed sample or an unreviewed unit cannot create or
prune a baseline: missing evidence must be obtained, not waived.

The baseline must not live under `.council/`: that directory is gitignored.
Commit it at a normal repository path, for example `council-baseline.json` or
`review/council-baseline.json`, and review its changes like code.

## Use a baseline

```sh
council review --baseline council-baseline.json
council ci --baseline council-baseline.json
council pr 123 --baseline council-baseline.json
```

- `review` reads the working-tree baseline; a relative path is resolved from the
  reviewed repository root.
- `ci` and `pr` read the baseline from the **base revision by default**. The
  path must be repository-relative. A PR cannot edit the baseline to silence a
  finding introduced by the same PR.
- `--baseline-from-base` makes `review` use the base revision too.
- `--allow-baseline-change` is the explicit maintenance bypass for a diff that
  intentionally edits the baseline. Without it, a changed baseline is a start
  failure (exit 3).
- `--baseline-strict` makes any expired or stale entry fail the gate. Without
  strict, stale entries are reported and can be pruned; expired entries never
  suppress anything.

Exit codes are unchanged: **0** pass, **1** fail, **2** incomplete, **3** could
not start.

## File format

```json
{
  "version": 1,
  "entries": [
    {
      "fingerprint": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
      "dimension": "security",
      "severity": "high",
      "file": "src/auth.py",
      "line": 42,
      "claim": "The token is logged.",
      "proof": "[[\"present\",{\"line\":42,\"path\":\"src/auth.py\",\"text\":\"log(token)\"}]]",
      "owner": "platform-team",
      "reason": "Legacy path; removal tracked in AUTH-221",
      "created": "2026-11-12",
      "expires": "2027-02-10"
    }
  ]
}
```

The fingerprint is:

```text
sha256(json([dimension, severity, file, normalized_claim, proof]))
```

It deliberately excludes the finding's line number as a separate field but the
proof usually contains its target line. Moving a target therefore creates a new
fingerprint; re-baseline only after deciding the new location is the same
accepted risk. Severity is included: escalating a high finding to critical is a
new gate decision, not an old waiver. Claim whitespace is normalized; wording is
otherwise part of the identity.

Entries require an owner, a reason, and an expiry not before their creation.
`created` and `expires` are ISO dates. Expired entries are reported and never
suppress anything. Unknown keys, duplicate fingerprints, malformed dates, an
empty owner/reason and a symlinked file are refused.

## Prune

After a finding is fixed, remove its entry rather than waiting for expiry:

```sh
council baseline prune \
  --baseline council-baseline.json \
  --from .council/runs/after

# Add --write to replace the file; without it the command only reports.
council baseline prune --write ...
```

Pruning compares the baseline with the proven blocking findings of the supplied
run. An entry whose finding is no longer present is stale. Expired entries are
not automatically pruned; expiry is a gate decision, not a cleanup.

## Trust rules

1. A baseline is a policy file, not evidence. It is reviewed and committed.
2. In CI, it is read from the base revision. A contribution cannot edit its own
   baseline in the same change.
3. A baseline that is itself changed in the reviewed diff is refused unless the
   maintainer passes `--allow-baseline-change`.
4. A missing, symlinked, non-regular, non-UTF-8 or oversized baseline is a start
   failure, before a reviewer is called.
5. The baseline can suppress only `PROVEN` blocking findings. It cannot suppress
   an `UNRUNNABLE`, an `UNSETTLED`, a missing sample, an unreviewed unit, or a
   start failure.

## Verification

```sh
nix develop -c python -m pytest tests/test_baseline.py tests/test_run.py
nix develop -c ./bin/council-verify --check docs/CLAIMS.md
```
