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

Use the `openspec` skill for the loop: `openspec instructions`, `openspec
validate --strict`, and `openspec archive`. The `openspec` CLI is pinned to
1.15.0 in the gate workflow.

## Dependency maintenance

Dependency sources have a weekly automated check: Dependabot for GitHub Actions
and Python, and the `dependencies` workflow for the Nix flake lock. Updates are
pull requests; the gate must pass and a human merges them. No workflow enables
auto-merge.

## Verification

The normal gate is authoritative: `nix flake check`, pytest, mypy, pyright,
ruff F/E9, `./bin/council-verify`, `tools/mutation_check.py`, and
`openspec validate --all --strict`. Do not replace a failing check with prose.
