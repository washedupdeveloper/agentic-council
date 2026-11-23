# Proposal

## Why

Model choice is manual and sticky today: the council reviewer profile pins one model, and a coding session uses whatever profile happens to be active. Surplus Intelligence sells the same model at several effective prices that move hourly, and the public coding boards disagree enough that one ranking is misleading. The result is either paying frontier prices for mechanical work or running an underpowered model on a decision that cannot be undone.

## What Changes

- A selector that reads an OpenSpec change, classifies each task, and routes it under a conservative attempt-then-escalate policy.
- A provider-agnostic market snapshot with live-best and seven-day-realised prices, refreshed on a schedule and checked at first use.
- A per-change routing map, drafted by the selector and approved by the owner before any task is routed.
- HTML and versioned JSON reports with a mandatory generation timestamp, freshness badge, named price basis, callouts, numbered sources and a method section.
- A direct OpenAI-compatible reviewer adapter in council that reads explicit `COUNCIL_DIRECT_*` configuration and answers each sample with one provider request, without booting an agent.

## Capabilities

### New Capabilities

- `model-routing`: task classification, model selection, pricing provenance, reports and calibration.
- `direct-reviewer-adapter`: a profile-driven OpenAI-compatible reviewer that answers each sample with one request.

### Modified Capabilities

None.

## Impact

- New capability: `model-routing` (the selector skill and its CLI).
- New capability: `direct-reviewer-adapter` (the council reviewer adapter).
- The verdict engine, proof execution, merge contract and existing Hermes adapter are unchanged.
- Out of scope for this change: MCP surface, five-dimension execution, PDF output, runtime hot-swapping, and providers beyond the Surplus, OpenRouter and generic OpenAI-compatible adapters.
