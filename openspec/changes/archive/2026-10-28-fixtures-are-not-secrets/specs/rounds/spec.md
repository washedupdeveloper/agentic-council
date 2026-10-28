# Spec Delta

## ADDED Requirements

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
