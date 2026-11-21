## ADDED Requirements

### Requirement: The adapter uses explicit endpoint configuration

The direct adapter SHALL resolve the model and endpoint from `COUNCIL_DIRECT_*` environment variables and SHALL NOT parse another program's profile.

#### Scenario: A review selects the direct adapter

- **WHEN** a review runs with `--agent direct`
- **THEN** the adapter reads `COUNCIL_DIRECT_MODEL` and `COUNCIL_DIRECT_BASE_URL` and sends no request to any other model

### Requirement: One request per sample

The adapter SHALL answer each sample with exactly one provider request and SHALL NOT start an agent process.

#### Scenario: A review has three samples

- **WHEN** a review requests three samples
- **THEN** exactly three provider requests are made and no agent subprocess is started

### Requirement: Failures are distinguishable

The adapter SHALL report missing configuration as `ReviewerMissing` and any other failure as `OSError`.

#### Scenario: The configuration is missing

- **WHEN** `COUNCIL_DIRECT_MODEL` or `COUNCIL_DIRECT_API_KEY` is absent
- **THEN** the adapter raises `ReviewerMissing` and the review is a start failure

#### Scenario: The provider fails

- **WHEN** the provider returns a non-2xx response, an empty answer or a timeout
- **THEN** the adapter raises `OSError` and the existing retry path records the sample failure

### Requirement: Identity covers the instrument

The adapter SHALL include the model, the base URL, the prompt version and the temperature in its identity hash, and SHALL exclude the API key.

#### Scenario: Two endpoints use different models

- **WHEN** two configurations with different models are used for the same prompt
- **THEN** their identity hashes differ

### Requirement: The adapter does not use tools

The adapter SHALL send only the review prompt and SHALL NOT read or write repository files.

#### Scenario: A review runs

- **WHEN** the adapter answers a sample
- **THEN** it returns the provider's raw text and leaves the repository unchanged
