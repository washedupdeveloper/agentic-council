# delivery-gate Specification

## Purpose
The delivery gate runs every check on the system it gates, and the diagnostic command
compares the installed build with a named source tree. A declared system is a build
contract that must evaluate; it is not a CI leg unless the gate names it. A local check
reports the systems it omitted instead of making a cross-system claim.

## Requirements

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

### Requirement: The installed build can be compared with its source

The diagnostic command MUST compare the installed version with a named source
tree and MUST fail when they differ.

#### Scenario: Installed and source agree

- **WHEN** the installed version and the source version are equal
- **THEN** the check reports a match and exits zero

#### Scenario: Installed and source differ

- **WHEN** the installed version and the source version differ
- **THEN** the check reports both versions, exits non-zero, and names the source path

### Requirement: The shipped action manifest is a checked artifact

The delivery gate MUST parse the composite action manifest and MUST fail when
the manifest is not valid YAML or when a step embeds an action input inside
Bash source instead of passing it through the environment.

#### Scenario: The action manifest is invalid YAML

- **WHEN** the composite action contains an unquoted colon-space in a scalar
- **THEN** the gate fails, names the manifest, and the action cannot be published as valid

#### Scenario: An input reaches Bash as source

- **WHEN** a `run` step contains `${{ inputs.* }}` rather than an `env:` entry
- **THEN** the gate fails and names the step

### Requirement: Container tooling owns its workspace

Container tooling MUST create a unique workspace for each run, MUST refuse to
operate on a pre-existing path it did not create, and MUST accept an OCI image
index as well as Docker's manifest.

#### Scenario: The workspace already exists

- **WHEN** the chosen workspace path exists before the run starts
- **THEN** the tool refuses instead of deleting or overwriting it

#### Scenario: An OCI index has no Docker manifest

- **WHEN** the image directory contains an OCI index and no `manifest.json`
- **THEN** the tool reads the OCI index and materialises the layers

#### Scenario: A layer contains a path outside the root

- **WHEN** a layer entry would resolve outside the materialised root
- **THEN** the tool refuses the layer and leaves the workspace intact
