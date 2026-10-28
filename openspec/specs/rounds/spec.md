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

### Requirement: The reviewer prompt is bounded

The prompt given to a reviewer SHALL be bounded in size, and bounding it SHALL NOT alter the
record: the probe results written to the run directory SHALL stay complete.

#### Scenario: A probe reports more findings than the prompt can carry

- **WHEN** a probe's findings would carry the prompt past its budget
- **THEN** the reviewer is shown the highest-severity findings, capped per rule code
- **AND** the entry states the total and the count omitted by rule

#### Scenario: The record stays complete

- **WHEN** the prompt is built from a summarised digest
- **THEN** `probes.json` in the run directory still holds every finding
- **AND** a later incremental run compares against that complete record

### Requirement: The handover is an OpenSpec change

At the end of a round the orchestrator SHALL write its handover as an OpenSpec change under the
run directory, and the harness SHALL check its shape before presenting it.

#### Scenario: A round ends with open findings

- **WHEN** the gate reports findings the round did not clear
- **THEN** the run holds a change directory with a proposal, at least one requirement carrying a WHEN/THEN scenario, and tasks as checkboxes
- **AND** the requirements name observable behaviour and what verifies it, not finding ids

#### Scenario: The change is shaped wrongly

- **WHEN** the change is missing a proposal section, a scenario, or a task
- **THEN** the run records the structural problems in its verdict and its next-steps
- **AND** the handover is not presented as complete

### Requirement: Every surface renders from the change

Every surface that tells a reader what to do SHALL derive it from the round's OpenSpec change, and
SHALL NOT carry a second plan of its own.

#### Scenario: A validated change exists

- **WHEN** the round wrote a change that validates
- **THEN** the next-steps file states the change's requirements and its tasks verbatim
- **AND** the gate-derived digest is not printed beside them

#### Scenario: No validated change exists

- **WHEN** the round wrote no change, or wrote one that does not validate
- **THEN** the next-steps file says so on its first line
- **AND** it falls back to the gate-derived plan

#### Scenario: A surface outside the run

- **WHEN** a PR comment or a `/goal` contract describes a run
- **THEN** it names the change and its state rather than restating its requirements

### Requirement: A fixture is not a secret

The secret-scan probe SHALL distinguish a credential from a fixture, and SHALL allowlist a fixture
by its value rather than by its path, so that a real secret in the same file is still reported.

#### Scenario: A planted credential

- **WHEN** a tree contains a credential that no allowlist names
- **THEN** the probe reports it as a finding

#### Scenario: An allowlisted fixture

- **WHEN** the tree contains the fake credential this repository's own tests plant, or the
  placeholder SHA in the sanitiser skill's usage example
- **THEN** the probe reports no finding for it

#### Scenario: A real secret beside a fixture

- **WHEN** a genuine credential is added to a file that also contains an allowlisted fixture value
- **THEN** the probe reports the credential, because the allowlist matches values and not paths

### Requirement: A handover accepts every shape the spec tool accepts

The handover validator SHALL accept every change the pinned CLI validates, and SHALL NOT require
more of a change than that CLI requires.

#### Scenario: A change with no delta

- **WHEN** a change carries `skip_specs: true` because it is prose, tooling or documentation
- **THEN** the validator accepts it, and does not report a missing `specs/<capability>/spec.md`

#### Scenario: A removed requirement

- **WHEN** a delta removes a requirement under `## REMOVED Requirements`
- **THEN** the validator does not demand a scenario of it, because the block is a reason and a
  migration note rather than a behaviour

#### Scenario: A requirement with behaviour

- **WHEN** a delta adds or modifies a requirement
- **THEN** the validator requires at least one scenario carrying both **WHEN** and **THEN**
