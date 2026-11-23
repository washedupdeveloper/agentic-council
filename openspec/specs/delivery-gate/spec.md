# delivery-gate Specification

## Purpose
The delivery gate runs every check on every Linux system the project declares, and the
diagnostic command compares the installed build with a named source tree. A local check
reports the systems it omitted instead of making a cross-system claim.

## Requirements

### Requirement: Every declared Linux system is gated

The delivery gate MUST run its checks on every Linux system the project declares
as supported.

#### Scenario: CI runs the gate

- **WHEN** the gate runs in CI
- **THEN** it checks x86_64-linux and aarch64-linux

#### Scenario: A local check omits a system

- **WHEN** a local `nix flake check` omits a declared system
- **THEN** the result names the omission and does not claim that system

### Requirement: The installed build can be compared with its source

The diagnostic command MUST compare the installed version with a named source
tree and MUST fail when they differ.

#### Scenario: Installed and source agree

- **WHEN** the installed version and the source version are equal
- **THEN** the check reports a match and exits zero

#### Scenario: Installed and source differ

- **WHEN** the installed version and the source version differ
- **THEN** the check reports both versions, exits non-zero, and names the source path
