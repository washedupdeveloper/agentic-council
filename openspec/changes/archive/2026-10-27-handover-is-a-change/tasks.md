# Tasks

## 1. Author it

- [x] 1.1 Extend the goal-review prompt: the orchestrator writes the change, with the layout and
      the requirement/scenario rules stated, and writes it into the run, never the repo.
- [x] 1.2 Requirements come from classes of findings, reusing the target's capability path when it
      already carries `openspec/specs/`.

## 2. Check it

- [x] 2.1 `validate_handover()` encodes the shape rules: proposal sections, a requirement per
      capability, WHEN and THEN per scenario, checkbox tasks.
- [x] 2.2 Tests cover a valid change, an absent one, and each malformed shape, and accept a real
      archived change produced by the toolchain.

## 3. Record it

- [x] 3.1 The verdict, the console output and `outcome.json` carry the handover and its validity.
- [x] 3.2 `next-steps.md` points at the change, or names the problems.
- [x] 3.3 `nix flake check --keep-going` passes.
