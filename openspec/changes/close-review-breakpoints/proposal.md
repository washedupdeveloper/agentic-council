# Proposal

## Why

The single-reviewer path has three remaining places where a run can look
cleaner or tidier than the evidence supports:

- two distinct claims on one line are merged into one finding;
- auto-sampling can conclude from one clean sample;
- strict proof mode can pass a blocking finding proven only by quotation.

The gate's own mutation table also contained a stale entry after the direct
adapter was added. These are reliability defects in the review verdict, not
feature requests.

## What Changes

- Merge findings by file, line and **normalized claim**, not by place alone.
- Require **two clean samples** before auto-sampling concludes PASS.
- Make strict proof mode **fail closed**: a blocking finding proven only by a
  quotation is INCOMPLETE, never PASS.
- Keep every merged claim, proof and evidence file in the verdict.
- Treat unknown reviewer dimensions and missing proofs as failed samples, not
  as silently dropped findings.
- Stop shipping the dev-only `council-verify` tool in the runtime application.
- Relax the build requirement to the setuptools version the locked nixpkgs
  provides, so the runtime package can be built.
- Repair the stale adapter mutation and record the remaining deployment limits
  in the design record.

## Capabilities

### New Capabilities

- `review-reliability`: the verdict's fail-closed rules for merging, sampling,
  proof strength and malformed reviewer output.

### Modified Capabilities

None.

## Impact

- `domain/merge.py`, `domain/schema.py`, `domain/adjudication.py`,
  `domain/verdict.py`, `domain/findings.py`, `run.py`, `runstore.py`,
  `pyproject.toml`.
- Existing tests and claims that describe one place as one finding; those
  become one claim as one finding.
- No new runtime dependency, no new service, no panel or multi-agent run.
- The change is deliberately fail-closed at the cost of more rows and, on a
  clean unit, one extra sample.
