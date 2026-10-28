# Spec Delta

## ADDED Requirements

### Requirement: A pass is only for work the probe did

A probe SHALL score a pass only for work it performed. Where a tool can evaluate without building,
the evaluation SHALL NOT be reported as the build's result.

#### Scenario: A gate that evaluates and builds

- **WHEN** the flake-check probe runs against a repository whose checks are derivations
- **THEN** it builds them, and scores 100 only if the build exits successfully

#### Scenario: A red build after a green evaluation

- **WHEN** evaluation succeeds and the build fails
- **THEN** the probe scores 0 and reports the build's findings, not "passed"

#### Scenario: A build that does not finish

- **WHEN** the build exceeds the probe's timeout
- **THEN** the probe reports no signal and says the gate was not measured, because unmeasured is not
  correct

#### Scenario: The toolchain is absent

- **WHEN** the pinned toolchain is unavailable
- **THEN** the probe reports that it did not run, rather than scoring it either way
