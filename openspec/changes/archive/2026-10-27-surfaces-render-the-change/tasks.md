# Tasks

## 1. Render from the change

- [x] 1.1 `read_handover_plan()` returns the change name, its requirements and its tasks verbatim.
- [x] 1.2 `render_next_steps()` prints them and returns; the A/B digest is only the fallback, and
      the fallback says it is one.

## 2. Point at it elsewhere

- [x] 2.1 The console verdict prints the change path and validity.
- [x] 2.2 `council pr` names the change from `outcome.json` without re-parsing the change.
- [x] 2.3 The `/goal` contract says the plan is the change.

## 3. Verify

- [x] 3.1 `nix flake check --keep-going` passes.
- [x] 3.2 A real run's verdict renders next-steps from its own change — checked against the run in
      `/tmp/council-handover-test`.
