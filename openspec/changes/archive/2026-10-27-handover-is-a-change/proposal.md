# Proposal

## Why

The council's top-level output is prose. `next-steps.md` is rendered by the harness from the gate
verdict, and the orchestrator's own reply is a terse control message. Both are readable, and
neither is actionable in the form every repository here already uses: a change directory with a
proposal, requirements that carry WHEN/THEN scenarios, and tasks as checkboxes.

Measured on the `hermes-agent` run: the handover named three blocking findings and the exact
command that verifies each, in a shape no container in this fleet can act on without a person
re-deriving the requirements by hand — which is the work `to-spec` and `openspec` exist to remove.

## What Changes

- The orchestrator writes the handover as an **OpenSpec change** under the run directory:
  `handover/openspec/changes/<slug>/{proposal.md, specs/<capability>/spec.md, tasks.md}`.
- It is written into the run, never into the target repository: a review is a read.
- The harness validates the change's **shape** and records the result in the verdict, the console
  output and `next-steps.md`. `openspec validate` cannot run inside a review — the runtime image
  has no Node — so the same rules are encoded once in `validate_handover()`.
- A handover that is absent or malformed is a recorded deviation, never a silent success.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `rounds`: adds the requirement that the handover is an OpenSpec change whose shape is checked.

## Impact

`scripts/council_loop.py` (the goal-review prompt, `validate_handover()`, the recording),
`tests/test_handover.py`, `next-steps.md` gains a section pointing at the change. No change to
probing, merging, scoring or the CLI surface.
