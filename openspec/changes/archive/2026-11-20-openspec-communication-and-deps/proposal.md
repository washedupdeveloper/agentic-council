# Proposal

## Why

Work briefs, task assignments and handoffs currently live in conversation and
disappear when the session ends. Subagents receive free-form context that can
drift from the change being reviewed, and dependency freshness has no recurring
gate. The repository needs a durable communication substrate and a weekly
dependency check that CI can verify.

## What Changes

- Bootstrap `openspec/` in `agentic-council-v2`.
- Add an `AGENTS.md` contract: every work item, task assignment, status update
  and handoff identifies an OpenSpec change and its task IDs; chat is a pointer
  to the artifact.
- Add OpenSpec validation to the `gate` workflow.
- Add weekly dependency automation:
  - Dependabot for GitHub Actions and Python dependencies.
  - A scheduled Nix flake-lock refresh that opens or updates a pull request.
  - No auto-merge; every update is CI-gated.

## Capabilities

### New Capabilities

- `agent-collaboration`: durable work items, subagent briefs and status handoffs.
- `dependency-maintenance`: recurring dependency checks and update pull requests.

### Modified Capabilities

None.

## Impact

`AGENTS.md`; `openspec/`; `.github/workflows/gate.yml`; new dependency workflow;
new Dependabot configuration; tests and documentation. No review-engine behavior
changes.
