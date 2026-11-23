# Design

## Context

See `proposal.md` for the motivation. The review engine already fails closed at
the verdict boundary. The remaining gaps are delivery and process gaps: a
declared platform that is never checked, an installed build that can drift from
the source, a reduced-evidence run that is not marked as such, a selector change
that cannot close because profile emission is missing, and a milestone loop that
only works when a person drives every agent.

## Goals / Non-Goals

**Goals:**

- Every declared Linux system is checked, or it is not declared.
- A stale installed build is detected before it is trusted.
- A one-sample review cannot happen by accident.
- A profile write changes only the model, provider and reasoning keys.
- The milestone runner can execute an OpenSpec change without a person typing
  every command, and still stops at every irreversible action.

**Non-Goals:**

- No new model, provider, panel or review dimension.
- No automatic commit, push, merge or profile creation without approval.
- No replacement for the council verdict gate.
- No cross-system claim from a host that did not run the system.

## Decisions

### D1. Gate both declared Linux systems

The CI gate runs on `ubuntu-24.04` and `ubuntu-24.04-arm`, each with
`nix flake check`. A local run still reports the omitted systems; it never
claims them. If an arm runner is unavailable, the correct fallback is to remove
`aarch64-linux` from the flake, not to leave it declared and ungated.

Why: a declared platform with no check is a false claim. The cost is roughly
double CI minutes; the benefit is that the flake's `systems` list is backed by a
run.

### D2. Doctor compares the installed version with a named source tree

`council doctor --source <repo>` reads `pyproject.toml` from the source tree,
compares its `project.version` with the installed distribution version, and
fails on a mismatch. The check does not claim that the code is identical; the
source build and the wheel check are the code proof. It catches the common
failure: a profile or PATH points at an older installed build.

Why: the installed binary and the source tree are separate artifacts. A version
comparison is cheap, deterministic and catches the drift that made the `direct`
adapter appear missing. A commit hash comparison would need the installed build
to record its source commit; that is a larger change and is not required to
close the failure.

### D3. A single sample is an explicit opt-in

`--samples 1` is refused unless `--allow-single-sample` is also supplied. The
default remains automatic (two clean, three on disagreement). The shipped action
exposes `allow-single-sample` as an input, default false, and passes it only
when the caller sets both `samples: 1` and the opt-in.

Why: the automatic policy is the safety property; a fixed one-sample run is a
deliberate reduction in evidence. Making it explicit keeps the old capability
for a caller who wants a cheap review and removes the accidental path. The cost
is a breaking change for scripts that used `--samples 1`; the opt-in is the
migration.

### D4. Profile emission is a line-targeted patch

The selector patches only `model.default`, `model.provider`, `model.base_url`
and, when requested, `model.reasoning_effort` inside the top-level `model:`
block. Every other line, comment and file is left untouched. It writes a
timestamped backup, prints a unified diff, and replaces the file atomically. The
ambient profile requires `--force`. A missing profile is not created unless
`--create-profiles` is set, and creation goes through `hermes profile create`.

Why: a YAML round-trip rewrites comments and ordering, which would change files
the selector does not own. A line patch is smaller, testable and preserves the
persona and provider blocks. Unusual layouts (flow style, anchors, a `model:`
block that is not a mapping) are refused rather than guessed.

### D5. The milestone runner enforces the approval boundary itself

The runner reads the OpenSpec change and its tasks, writes one prompt per task,
and invokes `hermes -p <profile> chat --query-file ... --oneshot`. A one-shot
has no TTY to answer approval prompts, so the default worker runs with `--yolo`
and a PATH shim refuses `git commit`, `git push` and `hermes profile`; the shim,
not the model, is the approval boundary. `--strict-approvals` omits `--yolo` for
an owner who wants to answer prompts in a TTY. The runner requires
`collab/<task>.md`, runs the task predicate, and ticks the box only after the
predicate passes. It may read, run tests and write workspace files; it never
invokes those three commands. The runner prints the commit and push commands
for the owner to run.

Why: "autonomous" must not mean "irreversible". The boundary is enforced by the
runner's command set and a shim, not by asking the model to behave. The cost is
that a task that needs a profile change stops; that is the intended approval
point.

### D6. The milestone record is M35

The archived change stays closed. This change is the follow-up, and its record
is `docs/M35.md`; the existing M34 record gains a pointer to it.

## Risks / Trade-offs

- **CI minutes double.** Mitigation: the gate is the only place both systems
  run; a local check stays fast and reports the omission.
- **The doctor check sees versions, not commits.** Mitigation: the source build
  and wheel check remain the code proof; the version check catches stale
  installs.
- **`--samples 1` breaks existing scripts.** Mitigation: the opt-in is explicit
  and documented; the error names it.
- **A line patch can miss an unusual YAML layout.** Mitigation: refuse a
  non-mapping `model:` block or a flow-style block instead of guessing.
- **The default worker uses `--yolo`.** Mitigation: the PATH shim refuses the
  irreversible commands; `--strict-approvals` omits it for a TTY.
- **The selector closure is a separate change.** Mitigation: this change's tasks
  name it and its archive is evidence, not an assumption.

## Migration Plan

1. Add the CI matrix; keep the local gate.
2. Add the doctor source check; no existing invocation changes.
3. Add the single-sample opt-in; update the action and the docs.
4. Implement profile emission; keep the default report-only path.
5. Close the selector change with its tasks and evidence.
6. Add the runner; it is a maintainer tool, not a shipped verb.
7. Record M35.

## Open Questions

None that change the contracts above.
