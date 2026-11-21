## ADDED Requirements

### Requirement: The adapter uses the selected profile

The direct adapter SHALL resolve the model and endpoint from the reviewer profile selected for the run.

#### Scenario: A review selects a profile

- **WHEN** a review runs with a named reviewer profile
- **THEN** the adapter reads that profile's model and provider endpoint and sends no request to any other model

### Requirement: One request per sample

The adapter SHALL answer each sample with exactly one provider request and SHALL NOT start an agent process.

#### Scenario: A review has three samples

- **WHEN** a review requests three samples
- **THEN** exactly three provider requests are made and no agent subprocess is started

### Requirement: Failures are distinguishable

The adapter SHALL report a missing profile or model as `ReviewerMissing` and any other failure as `OSError`.

#### Scenario: The profile is missing

- **WHEN** the selected profile or its model cannot be read
- **THEN** the adapter raises `ReviewerMissing` and the review is a start failure

#### Scenario: The provider fails

- **WHEN** the provider returns a non-2xx response, an empty answer or a timeout
- **THEN** the adapter raises `OSError` and the existing retry path records the sample failure

### Requirement: Identity covers the instrument

The adapter SHALL include the model, the base URL and the selected profile's bytes in its identity hash.

#### Scenario: Two profiles use different models

- **WHEN** two profiles with different models are used for the same prompt
- **THEN** their identity hashes differ

### Requirement: The adapter does not use tools

The adapter SHALL send only the review prompt and SHALL NOT read or write repository files.

#### Scenario: A review runs

- **WHEN** the adapter answers a sample
- **THEN** it returns the provider's raw text and leaves the repository unchanged
