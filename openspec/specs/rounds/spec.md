# Round Specification

## Purpose

What one review round guarantees: independent samples, a deterministic merge, and a gate that
decides from measurements rather than opinions.

## Requirements

### Requirement: A round samples the reviewer

A round SHALL run the configured number of reviewer samples in parallel, each in its own
profile and working directory, and SHALL merge their findings per claim.

#### Scenario: Samples disagree

- **WHEN** two samples report the same defect with different wording
- **THEN** the merge produces one claim
- **AND** the sample count is recorded on it

#### Scenario: Samples arrive late

- **WHEN** the round times out before every sample file exists
- **THEN** `council.py merge` recovers the files that landed
- **AND** the gate scores the recovered round

### Requirement: The gate decides from measurements

The gate SHALL compute the five dimension scores from the probe results, compare the aggregate
with the calibrated threshold, and stop on `k` consecutive rounds within `epsilon`.

#### Scenario: A passing round

- **WHEN** the aggregate meets the threshold and no high or critical claim is open
- **THEN** the verdict is satisfied
- **AND** `next-steps.md` names what is left

#### Scenario: A failing round

- **WHEN** a high or critical claim remains open
- **THEN** the verdict is not satisfied
- **AND** the fixer receives that claim, not the whole report

### Requirement: The fixer stops at proof

The fixer SHALL change the narrowest layer that removes the claim, add the regression proof,
and stop when the gate passes.

#### Scenario: A fix that spreads

- **WHEN** a fix would touch code outside the claim's boundary
- **THEN** it is not made in that round
- **AND** the reason is recorded in the next-steps
