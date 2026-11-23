# Tasks

## 1. Contract

- [x] 1.1 Write the proposal, design and spec deltas for `close-milestone-residuals`.
- [x] 1.2 Validate the change with `openspec validate close-milestone-residuals --strict`.

## 2. Aarch64 gate

- [x] 2.1 Add a CI matrix for `x86_64-linux` and `aarch64-linux` to the gate workflow.
- [x] 2.2 Add a governance test that the workflow names both systems.
- [x] 2.3 Record that a local `nix flake check` reports omitted systems and does not claim them.

## 3. Installed/source doctor

- [x] 3.1 Add `council doctor --source <repo>` and a version comparison check.
- [x] 3.2 Report a match, a mismatch and a missing source as distinct outcomes; exit non-zero on mismatch.
- [x] 3.3 Add tests for match, mismatch and missing source.
- [x] 3.4 Add a claim and update the doctor documentation.

## 4. Single-sample opt-in

- [x] 4.1 Add `--allow-single-sample` and refuse `--samples 1` without it.
- [x] 4.2 Record the opt-in in `verdict.json` and the reason.
- [x] 4.3 Expose `allow-single-sample` in the shipped action; pass it only with `samples: 1`.
- [x] 4.4 Add tests for refusal, acceptance and the automatic policy; update the docs.

## 5. Selector profile emission

- [x] 5.1 Add `--emit-profiles`, `--create-profiles`, `--dry-run` and `--profile-reasoning` to the selector CLI.
- [x] 5.2 Patch only `model.default`, `model.provider`, `model.base_url` and the optional reasoning key; preserve every other line and comment.
- [x] 5.3 Write a timestamped backup, print a unified diff and replace the file atomically.
- [x] 5.4 Protect the ambient profile with `--force`; print the `hermes profile create` command for a missing profile.
- [x] 5.5 Add tests for comments, persona, backup, diff, atomic write, ambient protection and missing profiles.

## 6. Close the selector change

- [x] 6.1 Run the selector suite and the from-scratch end-to-end script.
- [x] 6.2 Tick every `model-routing-selector` task with evidence and fill the capability purposes.
- [x] 6.3 Archive `model-routing-selector` and record the archive id.

## 7. Milestone runner

- [x] 7.1 Add `tools/milestone.py` with `plan`, `run` and `status` actions.
- [x] 7.2 Read the change, tasks and routing map; write one prompt per task from the OpenSpec template.
- [x] 7.3 Run `hermes -p <profile> chat --query-file ... --oneshot`; default `--yolo` with a refusing PATH shim, `--strict-approvals` to omit it; require `collab/<task>.md`.
- [x] 7.4 Run the task predicate; tick the box only after it passes; stop on failure.
- [x] 7.5 Refuse `git commit`, `git push` and `hermes profile` through a PATH shim; print the owner commands instead.
- [x] 7.6 Add tests with a fake `hermes` script, a fake predicate, a passing task and a failing task.

## 8. Record and close

- [x] 8.1 Run the full test suite, mypy, ruff, claims, mutations and `nix flake check`.
- [x] 8.2 Write `docs/M35.md` and add the pointer from M34.
- [x] 8.3 Render the M35 verdict page from the change artifacts.
- [x] 8.4 Archive `close-milestone-residuals` and record the final evidence.

## Evidence

| Check | Command | Result |
|---|---|---|
| Council suite | `nix develop -c python -m pytest` | 810 passed |
| Selector suite | `nix develop ~/projects/review-council-v2 -c python -m pytest tests/unit/test_model_routing.py -q` | 82 passed, 14 subtests |
| From-scratch e2e | `nix develop ~/projects/review-council-v2 -c bash tests/e2e/run_from_scratch.sh` | `e2e ok`, $15.40 at `5978473` |
| Claims | `nix develop -c ./bin/council-verify --check docs/CLAIMS.md` | 249/249 |
| Mutations | `python tools/mutation_check.py` | 72/72 caught |
| Flake | `nix flake check` | all checks passed; omitted `aarch64-linux` locally |
| OpenSpec | `openspec validate --all --strict` | 5 specs, strict-valid before the archive |
| Milestone runner | `nix develop -c python -m pytest tests/test_milestone.py -q` | 10 passed |
| Archive | `openspec archive close-milestone-residuals --yes` | archived as `2026-11-22-close-milestone-residuals` |
| OpenSpec after archive | `openspec validate --all --strict` | 7 specs, strict-valid |
