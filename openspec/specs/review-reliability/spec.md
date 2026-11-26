# review-reliability Specification

## Purpose
The review verdict is a fail-closed decision over merged, evidence-backed findings:
distinct claims survive merge, a clean result is confirmed by two samples, malformed
reviewer output cannot become a clean result, and a blocking claim proven only by
quotation cannot pass a strict run. The shipped gate uses the same automatic sample
policy unless the caller supplies an explicit count.

## Requirements

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

### Requirement: The shipped review gate does not pin one sample by default

The shipped review gate MUST use the automatic sample policy unless the caller
supplies an explicit sample count.

#### Scenario: The gate runs without a sample count

- **WHEN** the shipped gate is invoked without an explicit sample count
- **THEN** it uses the automatic policy and does not pass a fixed count of one

#### Scenario: The caller supplies a sample count

- **WHEN** the caller supplies an explicit sample count
- **THEN** the gate passes that count and the automatic policy is not used

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

#### Scenario: A reviewer finding has no proof

- **WHEN** a reviewer finding omits the proof required by the contract
- **THEN** the sample is rejected by the schema and the run cannot PASS

#### Scenario: A finding has no attempted proof outcome

- **WHEN** a finding reaches adjudication with no proof outcome
- **THEN** the finding is UNSETTLED and a blocking run is INCOMPLETE

### Requirement: The verdict keeps every merged wording

The published verdict MUST carry every distinct wording merged into a finding.

#### Scenario: Two samples word one claim differently

- **WHEN** the same file, line and normalized claim has two wordings
- **THEN** the verdict carries both wordings and every source sample

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

### Requirement: Proof infrastructure failures are unrunnable

A proof whose command fails because the proof environment lacks a dependency MUST
be `UNRUNNABLE`, never `REFUTED`; a missing tool is not counter-evidence.

#### Scenario: A repro imports a module the sandbox does not have

- **WHEN** a `repro` command exits non-zero with `ModuleNotFoundError`
- **THEN** the proof outcome is `UNRUNNABLE` and names the missing module

#### Scenario: A command expectation sees a missing dependency

- **WHEN** a `command` proof exits non-zero because its interpreter cannot import a module
- **THEN** the proof outcome is `UNRUNNABLE`, even when the expectation was non-zero

### Requirement: A stale line reference does not disprove its quote

A `present` proof whose quoted text is found at a different line in the same
file MUST be `UNRUNNABLE` and MUST name the line where the text actually occurs.

#### Scenario: The quote is one line above the cited line

- **WHEN** the cited line does not match but the same text occurs elsewhere in the file
- **THEN** the outcome is `UNRUNNABLE` with the actual line in the detail

#### Scenario: The quote is absent from the file

- **WHEN** the quoted text occurs nowhere in the file
- **THEN** the outcome remains `REFUTED`

### Requirement: A reviewed change cannot supply its own rules

A review MUST refuse a change that edits one of the rule documents configured to
govern it, unless the caller explicitly allows a rule change.

#### Scenario: The diff edits a governing rule document

- **WHEN** a configured rule document is changed by the reviewed diff and the caller has not opted in
- **THEN** the review is refused before any reviewer is asked and the reason names the rule document

#### Scenario: The caller deliberately changes a rule document

- **WHEN** the change edits a rule document and the caller passes the explicit opt-in
- **THEN** the review proceeds and records that rule changes were allowed

### Requirement: Command proofs cannot read the user's home

The command sandbox MUST keep the user's home directories out of the proof's
view; a repository located under a home directory remains readable.

#### Scenario: A proof reads a private home path

- **WHEN** a command proof names a file under `/home` or `/root`
- **THEN** the file is absent inside the sandbox and the proof cannot use it

#### Scenario: The repository is under a home directory

- **WHEN** the reviewed repository is under a home directory
- **THEN** the repository's own files are readable and a proof can run against them
