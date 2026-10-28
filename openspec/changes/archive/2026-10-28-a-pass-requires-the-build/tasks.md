# Tasks

## 1. Make the probe build

- [x] 1.1 Keep the eval pass as a fast-fail; award 100.0 only after a successful build.
- [x] 1.2 A timeout reports no signal instead of a pass.

## 2. Prove it

- [x] 2.1 Three tests: builds on the second call, red build scores 0, timeout scores nothing.
- [x] 2.2 `research/nix-tooling.md` says eval-only is not a pass.

## 3. Verify

- [x] 3.1 `pytest` — the probe suite and the whole suite.
- [x] 3.2 `nix flake check --keep-going` on this repository, gated on its exit code.
- [x] 3.3 `openspec validate --all --strict`.
