# Proposal

## Why

The upcoming feature request must start from one integrated `v2` branch. Two
Dependabot development branches are on the remote and the two older local
branches are already ancestors of `v2`; leaving the dependency branches open
would make the feature branch depend on a stale base.

## What Changes

- Merge every non-`v2` development branch into `v2`, preserving the branch
  commits.
- Merge the two Dependabot branches: the actions group and the Python group.
- Run the full repository gate after the merges and push the integrated `v2`.
- No review-engine behavior is intended to change; this is dependency and
  branch integration only.

## Capabilities

### New Capabilities

None; `skip_specs: true` records that no behavior change is intended.

### Modified Capabilities

None.

## Impact

`v2` history and dependency versions only. Any dependency-induced behavior change
is caught by the gate before the feature work starts.