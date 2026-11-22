## ADDED Requirements

### Requirement: A finding is identified by its claim, not only its place

The merge MUST keep distinct claims at the same file and line as distinct
findings, while merging the same normalized claim across samples.

#### Scenario: Two samples report the same claim at one place

- **WHEN** two samples report the same file, line and normalized claim
- **THEN** the verdict contains one finding with both samples and both evidence files

#### Scenario: Two samples report different claims at one place

- **WHEN** two samples report different claims at the same file and line
- **THEN** the verdict contains two findings, each with its own proof and evidence

#### Scenario: The same claim carries different dimensions

- **WHEN** samples report the same normalized claim with different dimensions
- **THEN** the finding takes the most blocking dimension and the highest severity

### Requirement: Auto-sampling never concludes from one clean sample

A clean result MUST require two clean samples in automatic sampling.

#### Scenario: Two clean samples

- **WHEN** the first and second samples contain no findings
- **THEN** the run reports two samples and may PASS

#### Scenario: The second sample finds something

- **WHEN** the first sample is clean and the second contains a finding
- **THEN** a third sample is requested and the run does not PASS on the first clean sample

#### Scenario: A sample fails

- **WHEN** any auto-sampled result has no usable output
- **THEN** the run is INCOMPLETE and names the failed sample

### Requirement: Strict proof mode fails closed

A blocking finding proven only by a static quotation MUST NOT produce PASS when
executed proofs are required.

#### Scenario: A quotation-only blocker under strict mode

- **WHEN** a blocking finding is PROVEN by a static proof and executed proofs are required
- **THEN** the run is INCOMPLETE and names the finding

#### Scenario: An executed blocker under strict mode

- **WHEN** a blocking finding is PROVEN by an executed proof and executed proofs are required
- **THEN** the run is FAIL

#### Scenario: A quotation-only non-blocking finding

- **WHEN** a non-blocking finding is PROVEN by a static proof and executed proofs are required
- **THEN** the run may PASS and the finding is named in the reason

### Requirement: Malformed reviewer evidence cannot become a clean result

Unknown dimensions, missing proofs and empty proof outcomes MUST fail closed.

#### Scenario: An unknown dimension

- **WHEN** a reviewer section is not one of the five dimensions
- **THEN** the sample is rejected by the schema and the run cannot PASS

#### Scenario: A finding has no proof

- **WHEN** a finding has no proof outcome
- **THEN** the finding is UNSETTLED and a blocking run is INCOMPLETE

### Requirement: The verdict keeps every merged wording

The published verdict MUST carry every distinct wording merged into a finding.

#### Scenario: Two samples word one claim differently

- **WHEN** the same file, line and normalized claim has two wordings
- **THEN** the verdict carries both wordings and every source sample
