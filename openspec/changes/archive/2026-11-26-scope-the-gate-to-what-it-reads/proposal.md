# Proposal

## Why

The gate was slow, and most of that time bought nothing.

`nix flake check` skips a check whose derivation is unchanged, so in principle a
touch of one file rebuilds only the checks that read it. In practice every check
took the whole tree as one input, so any edit changed every hash. **Measured:**
editing `README.md`, `docs/M35.md`, an OpenSpec spec, `CHANGELOG.md`,
`pyproject.toml`, `tools/release.py`, `tests/test_size.py` or
`src/council/claims.py` each rebuilt **11 of 12** checks. Only `nix-lint` stayed
cached, because it alone had its own root. The cache never hit, because nothing
was ever unchanged.

Separately, `council-mutations` ran 72 full-suite pytest runs in a serial loop
inside one derivation: **measured at 1911 s**, against 31 s for the suite itself.
One check was the gate.

## What Changes

- Each check declares the subtrees it reads, via `lib.fileset`. An edit outside a
  check's inputs leaves it cached.
- The mutation campaign scores its mutants across a bounded pool. Scheduling
  changes; what is proved does not.
- A test holds every scope to what its check actually opens, because a scope that
  is too narrow is a check that reads less and passes.

## Capabilities

### New Capabilities

- `build-scope`: a check's declared input is a superset of what it reads, and an
  edit outside that input does not invalidate the check.

## Impact

- `flake.nix`, `tools/mutation_check.py`, `tests/test_build_scope.py`,
  `claims.toml`, `docs/CLAIMS.md`
