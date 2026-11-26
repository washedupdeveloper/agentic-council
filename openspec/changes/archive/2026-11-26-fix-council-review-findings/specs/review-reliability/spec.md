# Spec Delta

## ADDED Requirements

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