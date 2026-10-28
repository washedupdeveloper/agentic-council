# Proposal

## Why

`validate_handover` rejects two change shapes that the pinned OpenSpec CLI validates and archives:

    retire-unsettleable-claims   `skip_specs: true`        -> "no specs/<capability>/spec.md"
    formatter-is-enforced        `## REMOVED Requirements` -> "requirement '...' has no scenario"

Both were found by this repository's own test — `test_a_real_archived_change_passes_this_check`
validates the real archive of a sibling checkout — which is exactly the cross-repository check that
was worth writing.

The validator is stricter than the tool it claims to check. A handover consumer that rejects a
change the CLI accepted turns a correct archive into a failed round, and the operator's remedy would
be to damage a valid change to please a validator.

## What Changes

- `skip_specs: true` in `.openspec.yaml` means the change carries no delta by design; the "no
  specs" problem is not raised.
- A requirement under `## REMOVED Requirements` is not asked for a scenario. A removal records what
  is gone and why — reason and migration — and has no behaviour left to describe.
- ADDED and MODIFIED requirements still require a scenario with **WHEN** and **THEN**, unchanged.

## Capabilities

### Modified Capabilities

- `rounds`: adds "A handover accepts every shape the spec tool accepts".

## Impact

`scripts/council_loop.py`. No behaviour change for a well-formed change with a delta; two false
rejections removed.
