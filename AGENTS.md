# AGENTS.md — working in agentic-council-v2

This repository is a review gate. A review is a claim until a check settles it;
the same rule applies to the work around the code.

## Work communication

Every non-trivial work item, task assignment, status update and handoff is an
OpenSpec change:

- Start with `openspec/changes/<name>/`; its proposal and `tasks.md` are the
  authoritative brief.
- A subagent brief names the change and the task IDs it owns. It does not carry a
  second prose brief that contradicts the change.
- A subagent returns the same change and task IDs, the files it changed, and the
  evidence commands it ran.
- Chat is a short pointer to the change, never the only record of the work.
- Pure refactors and dependency bumps use `skip_specs: true` when behavior does
  not change.

Use the `openspec` skill for the loop. The CLI comes from the flake —
`nix run .#openspec -- <command>` — so the version is the one in `flake.lock` and
nothing is installed into a profile.

### Done means archived

- A change with every task ticked is finished. Archive it in the same commit as the
  last task: `nix run .#openspec -- archive <name> --yes`.
  `tests/test_openspec_state.py` fails the gate on a finished change left open.
- A **decision** is a row in the change's `design.md`: the option taken, the options
  rejected, and what would falsify the choice. A decision that exists only in chat did
  not happen.
- A **verdict** on the work is a row in `tasks.md`: the claim, the command that settles
  it, and the result. "Done" without an evidence command is unproven.
- A **presentation** to the owner is rendered from the change — proposal, design, spec
  delta, tasks, evidence — not restated in chat. Chat carries the decision table and a
  pointer to the artifact.

## Dependency maintenance

Dependency sources have a weekly automated check: Dependabot for GitHub Actions
and Python, and the `dependencies` workflow for the Nix flake lock. Updates are
pull requests; the gate must pass and a human merges them. No workflow enables
auto-merge.

## Verification

The normal gate is authoritative: `nix flake check`, pytest, mypy, pyright,
ruff F/E9, `./bin/council-verify`, `tools/mutation_check.py`, and
`openspec validate --all --strict`. Do not replace a failing check with prose.
