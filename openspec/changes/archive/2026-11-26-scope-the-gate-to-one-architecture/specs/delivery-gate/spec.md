# Spec Delta

## MODIFIED Requirements

### Requirement: The gate names the one system it checks

The delivery gate MUST run its checks on x86_64-linux and MUST name the edit that
adds another system, so re-enabling a leg is a one-line change to the workflow
matrix.

#### Scenario: CI runs the gate

- **WHEN** the gate runs in CI
- **THEN** it checks x86_64-linux and the workflow comment names `ubuntu-24.04-arm` as
  the entry that adds aarch64-linux

#### Scenario: A declared system is not a gated system

- **WHEN** the flake declares `aarch64-linux` and the workflow matrix does not list an
  arm runner
- **THEN** the arm system still evaluates, and no run claims to have tested it

#### Scenario: A local check omits a system

- **WHEN** a local `nix flake check` omits a declared system
- **THEN** the result names the omission and does not claim that system


