# Tasks

## 1. Contract

- [x] 1.1 Write the proposal, design and `review-reliability` spec delta.
- [x] 1.2 Update the claims registry for claim-level merge, two-clean sampling and strict fail-closed behavior.

## 2. Merge by claim

- [x] 2.1 Key the merge by file, line and normalized claim instead of place alone.
- [x] 2.2 Add tests for same-claim merge, different-claim separation, dimension adjudication and preserved evidence.
- [x] 2.3 Update the existing one-place-one-finding tests and generated claims.

## 3. Two clean samples

- [x] 3.1 Make auto-sampling request a second sample after a clean first sample.
- [x] 3.2 Update `--plan`'s sample estimate and the state-machine documentation.
- [x] 3.3 Add tests for two clean samples, a finding on the second sample and a failed second sample.

## 4. Strict proof mode

- [x] 4.1 Make a quotation-only blocking finding INCOMPLETE under `--require-executed-proofs`.
- [x] 4.2 Add tests for the strict quotation, executed blocker and non-blocking quotation cases.
- [x] 4.3 Update the strict-mode claim and generated docs.

## 5. Malformed evidence and preservation

- [x] 5.1 Reject unknown dimensions and keep missing proofs at the schema boundary.
- [x] 5.2 Preserve every merged wording in `Finding` and `verdict.json`.
- [x] 5.3 Add the schema, empty-proof and wording-preservation tests.

## 6. Gate and close

- [x] 6.1 Repair stale mutations so the merge and adapter claims remain falsifiable.
- [ ] 6.2 Run the full test suite, mypy, ruff, claim verification and `nix flake check`.
- [x] 6.3 Stop shipping the dev-only `council-verify` in the runtime application.
- [x] 6.4 Record the deployment and cross-system limits in the design verdict.
- [ ] 6.5 Validate `close-review-breakpoints --strict` and record the final evidence.
- [ ] 6.6 Rebuild the installed Nix profile from HEAD and verify `council agents --json` lists `direct`.

## Evidence

| Check | Command | Result |
|---|---|---|
| Suite | `nix develop -c python -m pytest -p no:cacheprovider` | 788 passed |
| Types | `nix develop -c mypy src` | 58 files clean |
| Lint | `nix develop -c ruff check --select F,E9 src tools tests` | clean |
| Claims | `nix develop -c ./bin/council-verify` | 241/241 |
| Mutations | `nix develop -c python tools/mutation_check.py` | 69/69 |
| Flake | `nix flake check` | pending |
| OpenSpec | `nix shell nixpkgs#nodejs -c npx -y @fission-ai/openspec@1.15.0 validate close-review-breakpoints --strict` | valid |
| Installed adapter | `council agents --json` | pending |
