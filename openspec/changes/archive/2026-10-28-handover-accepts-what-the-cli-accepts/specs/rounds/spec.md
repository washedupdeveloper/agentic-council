# Spec Delta

## ADDED Requirements

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
