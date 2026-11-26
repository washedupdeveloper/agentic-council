# Spec-driven development

Every behaviour change in this repository starts as a spec, and the spec is only finished
when a test proves it. The loop is the same for a one-line fix and a new subsystem.

## The loop

1. **Propose.** `openspec/changes/<name>/proposal.md` — why, what changes, which
   capabilities. `openspec list --specs` first: the behaviour may already be specified.
2. **Specify.** `specs/<capability>/spec.md` — `## ADDED` / `## MODIFIED` / `## REMOVED`
   requirements. Every requirement carries at least one scenario
   (`#### Scenario:` with `WHEN` / `THEN` / `AND`). A requirement without a scenario is
   a slogan; `validate --strict` refuses it.
3. **Design.** `design.md` — the decisions as rows: option taken, options rejected, what
   would falsify the choice. A decision that exists only in chat did not happen.
4. **Test first.** Every scenario becomes at least one test whose name states the
   scenario. This is the part that makes the rest real: the scenario is the sentence, the
   test is the proof, and a spec whose scenarios have no tests is a document nobody
   checks. Write the test before the implementation; run it red; then make it pass.
5. **Task.** `tasks.md` — one task per commit. A ticked task names the test that proves
   it. The commit body names the tasks it closes.
6. **Evidence.** `tasks.md` ends with an `## Evidence` table:

   ```markdown
   ## Evidence

   | claim | command | result |
   |---|---|---|
   | a finished change is archived | `pytest tests/test_openspec_state.py -q` | 2 passed |
   ```

   One row per ticked task, and the command is the one you actually ran. "Done" without
   an evidence command is unproven, and an unproven task is not finished work.
7. **Archive.** `nix run .#openspec -- archive <name> --yes`, in the same commit as the
   last task. The gate fails on a finished change left open.

## What the gate enforces

| rule | where |
|---|---|
| the delta is structurally valid | `validate --all --strict`, every CI run |
| a finished change is archived | `tests/test_openspec_state.py` |
| an open change records its evidence | `tests/test_openspec_state.py` |
| no test skips | `COUNCIL_STRICT_SKIPS=1`; permits in `tests/permitted_skips.toml` |
| a claim is a sentence and a command | `claims.toml`, `council-verify` |
| a rule has a falsifier | `tools/mutation_check.py`, 72/72 |

## Testing for reliable automation

The gate is the only reader that cannot be argued with, so the tests are written for it:

- **No skips.** A skipped test is a pass that measured nothing. If a test cannot run
  here, it fails and says why; the only way past is an entry in
  `tests/permitted_skips.toml`, which the owner writes.
- **No network, no clock, no host.** A test that needs the internet or the wall clock is
  a test that fails for a reason unrelated to the change. Local processes, temp
  directories, fixed inputs.
- **A control for every guard.** Each check that can pass is paired with a case that
  proves it can fail — `tests/test_openspec_state.py` plants a finished change,
  `tests/test_claims.py` plants a skipping node, `tests/test_size.py` names its ratchet.
- **The default path is the tested path.** A library rule the shipped CLI bypasses is a
  rule nobody runs. Test the entry point users call, with its defaults.
- **Evidence is a command, not a claim.** If a sentence in `tasks.md` has no command
  behind it, it is unproven, and the next person cannot tell it apart from a guess.

## Why this and not a checklist

A checklist records that something was considered. A spec records what the system must
do, and a test records that it does it. The gap between those two is where every silent
regression lives — including three sandbox proofs that skipped in the gate for months
while the suite reported green.
