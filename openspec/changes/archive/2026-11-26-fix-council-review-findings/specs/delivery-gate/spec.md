# Spec Delta

## ADDED Requirements

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