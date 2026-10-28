# Tasks

## 1. Record the behaviour

- [x] 1.1 Add the requirement and its three scenarios to `rounds`.
- [x] 1.2 Confirm the implementation already satisfies it (`scripts/probes.py`, commit `390e58e`).

## 2. Verify

- [x] 2.1 `openspec validate fixtures-are-not-secrets --strict` passes.
- [x] 2.2 `pytest tests/test_probes.py` — both directions still pass.
- [x] 2.3 `nix flake check --keep-going` passes.
