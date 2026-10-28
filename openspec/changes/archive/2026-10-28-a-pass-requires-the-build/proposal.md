# Proposal

## Why

`probe_flake_check` ran `nix flake check --no-build --keep-going` and scored `rc 0` as 100.0 —
"flake check passed". `--no-build` evaluates the checks and stops. A run-tier check is a derivation,
so evaluation succeeds while the build fails: a repository whose `checks` were all red came back
green, with a perfect score, from a probe that never ran one of them.

This is the failure the council exists to find in other people's work, in the council.

## What Changes

- The probe keeps the eval pass as a cheap fast-fail, then **builds**. Only a build that exits 0
  scores 100.0.
- A build that does not finish inside the timeout is reported with **no signal**, not as a pass:
  unmeasured is not the same as correct.
- Three tests: the second call must not carry `--no-build`; a red build scores 0.0 with findings;
  a timeout scores nothing and says so.
- `research/nix-tooling.md` records that eval-only is not a pass.

## Capabilities

### New Capabilities

- `probes`: what a probe may claim. This repository's other findings are only as good as the
  probes' honesty, and nothing stated what that meant until now.

### Modified Capabilities

None.

## Impact

`scripts/probes.py`, `tests/test_probes.py`, `research/nix-tooling.md`. Runtime cost: a review now
builds the target's checks, which is minutes rather than seconds — the price of the probe meaning
what it says.
