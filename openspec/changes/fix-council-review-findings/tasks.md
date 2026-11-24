# Tasks

## 1. Contract

- [x] 1.1 Write the proposal, design and spec deltas for `fix-council-review-findings`.
- [x] 1.2 Validate the change with `openspec validate fix-council-review-findings --strict`.

## 2. Shipped action manifest

- [x] 2.1 Quote the `samples` description so the composite action is valid YAML.
- [x] 2.2 Pass every action input through `env:`; remove `GITHUB_PATH` and call the installed binary by absolute path.
- [x] 2.3 Add a governance test that parses the manifest and refuses `${{ inputs.* }}` inside a `run` step.
- [x] 2.4 Add PyYAML to the test environment and the `dev` extra; prove `yaml.safe_load` succeeds.

## 3. Proof adjudication

- [x] 3.1 Treat a missing module in a `repro` / `command` as `UNRUNNABLE`, not `REFUTED`.
- [x] 3.2 Make `present` search for a stale quote and return `UNRUNNABLE` with the actual line.
- [x] 3.3 Normalise `python` to `python3` when `python3` is the allowed interpreter.
- [x] 3.4 Add regression tests for each path.

## 4. Rule trust

- [x] 4.1 Refuse a review whose configured rule document is changed by the reviewed diff.
- [x] 4.2 Add `--allow-rules-change` and record the opt-in in the verdict reason.
- [x] 4.3 Read the rule configuration and rule documents from the index for a staged review.

## 5. Proof sandbox

- [x] 5.1 Mask `/home` and `/root` in the command sandbox while keeping a repository under a home readable.
- [x] 5.2 Reorder `tools/sandbox.sh` so a repository under `/tmp` is bound after the private tmpfs, not over it.
- [x] 5.3 Only mask a path that exists on the host, so the build sandbox does not fail on a missing `/home`.

## 6. Milestone runner

- [x] 6.1 Run acceptance predicates with the worker's guarded PATH.
- [x] 6.2 Keep mixed quoted/unquoted verify items, quoted `#` characters, doubled apostrophes and YAML escapes.
- [x] 6.3 Add tests for both parser cases and for a predicate that attempts a commit.

## 7. Mutation baseline

- [x] 7.1 Run the unmodified suite before scoring mutations and refuse a red baseline.
- [x] 7.2 Add a focused regression test for the red-baseline path.

## 8. MCP retention

- [x] 8.1 Reject empty, absolute and parent-segment run ids; resolve the candidate inside the retention root.
- [x] 8.2 Open the retained verdict through a directory file descriptor with `O_NOFOLLOW`.

## 9. Container tooling

- [x] 9.1 Create a unique image workspace and refuse an unowned path.
- [x] 9.2 Read an OCI index as well as Docker's manifest; verify blob digests; contain layer paths and whiteouts.
- [x] 9.3 Reject a parent segment in a layer path; handle absolute image links and directory replacement.

## 10. Record and verify

- [x] 10.1 Run pytest, mypy, pyright, ruff, claims and `openspec validate --all --strict`.
- [x] 10.2 Run the targeted Astra review of the change and record the findings.
- [x] 10.3 Record the outcome in `docs/M36.md`.

## Evidence

| Check | Command | Result |
|---|---|---|
| Council suite | `nix develop -c python -m pytest` | green |
| Claims | `nix develop -c env PYTHON=python ./bin/council-verify` | 262/262 |
| mypy | `nix develop -c mypy src` | 58 files, no issues |
| ruff F,E9 | `nix develop -c ruff check --select F,E9 src tools tests` | clean |
| pyright | `nix develop -c pyright` | 0 errors |
| OpenSpec | `npx @fission-ai/openspec@1.15.0 validate --all --strict` | 8 items passed |
| Targeted Astra review | `council review --agent direct --base 84ad62d --samples 1 --allow-single-sample` | six passes; every critical/high finding fixed and covered |
| `nix flake check` | `nix flake check --keep-going` | every check passed on x86_64-linux; aarch64 is gated by CI |