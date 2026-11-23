## ADDED Requirements

### Requirement: A single-sample review is an explicit opt-in

A review that requests one sample MUST be refused unless the caller explicitly
allows the reduced evidence.

#### Scenario: One sample without the opt-in

- **WHEN** a caller requests one sample and does not allow a single-sample run
- **THEN** the review is refused before the reviewer is asked and the reason names the opt-in

#### Scenario: One sample with the opt-in

- **WHEN** a caller requests one sample and allows a single-sample run
- **THEN** the review runs one sample and the verdict records that the reduced evidence was allowed

#### Scenario: The automatic policy

- **WHEN** a caller does not request a fixed sample count
- **THEN** the automatic policy applies and no opt-in is required
