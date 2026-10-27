# Proposal

## Why

The orchestrator now writes its handover as an OpenSpec change, but the surfaces around it did not
follow. `next-steps.md` still rendered its own A/B/C plan from the gate, the console verdict named
only a path, and `council pr` and `council goal` said nothing about a change at all. Two plans that
can disagree is worse than one plan in the wrong shape: the reader has to decide which is
authoritative, and the one they pick is the one they will follow.

## What Changes

- `next-steps.md` renders **from the change**: its requirements (capability + name) and its
  checkbox tasks verbatim, with a pointer to the change directory. The gate-derived A/B/C digest
  is not printed beside it, because two plans is the defect.
- A run that produced no validated change **says so** and falls back to the gate-derived plan.
- The console verdict prints the change path and whether it validates.
- `council pr` names the change, read from `outcome.json` — a pointer, not a second parser.
- The `/goal` contract states that the plan is the change the council writes into the run.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `rounds`: adds the requirement that every surface renders from the change.

## Impact

`scripts/council_loop.py` (`read_handover_plan`, `render_next_steps`, `write_outcome`),
`scripts/pr.py`, `scripts/goal.py`, `tests/test_surfaces.py`. No change to probing, scoring, the
gate or the CLI surface.
