# Proposal

## Why

The gitleaks allowlist landed as commit `390e58e` with no change record. It changed what the probe
reports — a repository adopting this config now sees zero findings where it saw three — and this
repository's rule is that a change to what a user sees gets a proposal and a delta.

The behaviour itself is right: the three findings were fixtures, not credentials, and the allowlist
names the fixture **values** rather than their paths, so a real secret added to the same file still
fires. What was missing is the requirement that says so, and therefore a test a future edit can
violate.

## What Changes

- `rounds` gains **A fixture is not a secret**: the probe distinguishes a credential from a fixture,
  allowlists by value, and three scenarios pin the three cases that matter — planted credential,
  allowlisted fixture value, real secret added to an allowlisted file.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `rounds`: adds the requirement above.

## Impact

`openspec/specs/rounds/spec.md` (one requirement). No code changes: `390e58e` already implements it,
and `tests/test_probes.py` already exercises both directions (48 tests).
