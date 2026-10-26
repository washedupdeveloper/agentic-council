# Spec Delta

## ADDED Requirements

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
