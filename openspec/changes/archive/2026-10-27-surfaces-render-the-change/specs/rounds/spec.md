# Spec Delta

## ADDED Requirements

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
