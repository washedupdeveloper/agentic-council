# Proposal

## Why

The archived `close-review-breakpoints` change closed the verdict's silent
failure paths, but five residuals remain: aarch64 is declared but not gated;
the installed binary can silently diverge from the source; a single-sample
review is possible without an explicit opt-in; `model-routing-selector` is 0/37
with profile emission unimplemented; and the milestone loop depends on hand-run
agents. Each is a place where the system can look complete while a guarantee is
unproven.

## What Changes

- Gate both declared Linux systems in CI: `x86_64-linux` and `aarch64-linux`.
- Add `council doctor --source <repo>`: compare the installed version with the
  source tree and report a mismatch as a failure.
- Require `--allow-single-sample` for `--samples 1`; the automatic policy stays
  the default, and the shipped action exposes the opt-in.
- Implement selector profile emission: `--emit-profiles`, `--create-profiles`
  and `--dry-run`; patch only the model, provider and optional reasoning keys;
  preserve comments, persona and unrelated configuration; back up, diff and
  write atomically; protect the ambient profile.
- Close `model-routing-selector`: tick its tasks with evidence, archive it, and
  give `model-routing` and `direct-reviewer-adapter` real purposes.
- Add an approval-aware milestone runner: it reads the OpenSpec change and
  tasks, runs the selected profile per task, requires `collab/<task>.md`
  evidence, runs the task predicate, and ticks the box only after it passes. It
  auto-runs reads, tests and workspace writes; it stops before commits, pushes
  and profile changes.
- Record the closure as M35.

## Capabilities

### New Capabilities

- `delivery-gate`: CI platform coverage and installed/source consistency.
- `milestone-runner`: the approval-aware loop that turns an OpenSpec change into
  executed, evidenced tasks.

### Modified Capabilities

- `review-reliability`: a single-sample review becomes an explicit opt-in.

## Impact

- `.github/workflows/gate.yml`, `src/council/doctor.py`, `src/council/cli.py`,
  `src/council/cli_parser.py`, `src/council/request.py`, `src/council/run.py`,
  `tests/`, `claims.toml`, `docs/`.
- `hermes-skills` selector: `scripts/surplus_select/`, its tests and `SKILL.md`;
  `model-routing-selector` is archived by this milestone.
- New `tools/milestone.py`, its tests, and a task-prompt template.
- No new runtime dependency. The runner uses the existing Hermes CLI and the
  selector's report.
- The selector closure is a separate OpenSpec change; this change records it and
  depends on its archive.
