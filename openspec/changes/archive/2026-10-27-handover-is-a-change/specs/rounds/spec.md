# Spec Delta

## ADDED Requirements

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
