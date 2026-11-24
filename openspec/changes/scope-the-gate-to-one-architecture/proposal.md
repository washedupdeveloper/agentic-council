# Proposal

## Why

The gate runs `nix flake check` twice, once on `ubuntu-24.04` and once on
`ubuntu-24.04-arm`. The arm leg has never failed for an architecture-specific
reason, and it doubles the wall-clock cost of every push. The owner does not use
arm, so the leg is minutes spent to prove a platform nothing runs on.

Removing it must not become a lie: `aarch64-linux` stays declared in the flake,
because a declared system is a build contract and the package must still
evaluate for it. What changes is the claim — CI tests one system, and says so.

## What Changes

- The gate matrix carries one entry, `ubuntu-24.04`.
- The workflow comment names `ubuntu-24.04-arm` and says that adding it is the
  whole edit, so re-enabling the leg is one word rather than a rewrite.
- `flake.nix` keeps `aarch64-linux` and says why: declared for evaluation, not
  gated by CI.
- The governance test and its claim assert the new shape — one gated system, the
  arm entry still named — so a silent removal of the pointer fails the gate.

## Capabilities

### Modified Capabilities

- `delivery-gate`: the gate names the one system it checks, and a declared
  system is explicitly not a gated one.

## Impact

- `.github/workflows/gate.yml`, `flake.nix`, `tests/test_governance.py`,
  `claims.toml`, `docs/CLAIMS.md`, `openspec/specs/delivery-gate/spec.md`

