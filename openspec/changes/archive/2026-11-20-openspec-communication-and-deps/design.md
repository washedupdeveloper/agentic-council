# Design

## Context

OpenSpec is the repository's durable artifact container. The review engine and
its verdict are unchanged by this work; the change governs how work is briefed,
delegated and reported, and how dependency updates reach the repository.

## Decisions

### Every work item has a change

A work item is represented by `openspec/changes/<name>/`. The proposal states
the problem, the spec delta states observable behavior, and `tasks.md` is the
work plan. A chat reply may summarise state but must name the change and task IDs;
it is not the brief.

### Subagent briefs are task references

A delegated task must name the change and the task IDs it owns. The subagent
returns the same IDs, the files it changed and the evidence commands it ran. A
subagent never receives a competing prose brief that is absent from the change.

### Dependency refresh is a pull request, never an auto-merge

Dependabot checks GitHub Actions and Python dependencies weekly. A scheduled
workflow runs `nix flake update` weekly and opens or updates a dedicated branch
and pull request only when `flake.lock` changed. The existing gate is required on
every dependency PR; a human decides when to merge. No workflow enables
auto-merge.

## Risks

The scheduled workflow needs `contents: write` and `pull-requests: write` to push
its branch and open the PR. It uses the repository token and cannot alter the
gate configuration. If branch protection blocks the bot, the workflow reports the
failure instead of silently succeeding.

## Migration

The first change is this one. Later behavior changes use the same loop; pure
refactors and dependency bumps set `skip_specs: true` when no behavior changes.
