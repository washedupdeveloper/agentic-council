# Tasks

## 1. Scope the gate

- [x] 1.1 Reduce the gate matrix to `ubuntu-24.04`.
- [x] 1.2 Name `ubuntu-24.04-arm` in the workflow comment as the enabling edit.
- [x] 1.3 Keep `aarch64-linux` in `flake.nix` and record why it is declared but
      not gated.

## 2. Hold the shape

- [x] 2.1 Replace the governance test with one asserting the single gated system
      and the surviving arm pointer.
- [x] 2.2 Update the claim and regenerate `docs/CLAIMS.md`.
- [x] 2.3 Update the `delivery-gate` capability spec.

## 3. Evidence

- [x] 3.1 `tests/test_governance.py` passes.
- [x] 3.2 `./bin/council-verify` holds.
- [x] 3.3 `nix flake check --keep-going` passes.
- [x] 3.4 `actionlint` reports nothing new for `gate.yml`.
- [x] 3.5 `openspec validate --all --strict` passes.

