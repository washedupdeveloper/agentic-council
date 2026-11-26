# mcp-resources Specification

## Purpose
Retained council verdicts are exposed through MCP resources without allowing a
resource request to read outside the configured retention directory.

## Requirements

### Requirement: A verdict resource stays inside the retention root

The MCP server MUST resolve a requested run id inside the configured retention
root and MUST reject a run id that resolves outside it.

#### Scenario: A run id contains a parent segment

- **WHEN** a resource request names `../secrets`
- **THEN** the server rejects it and no file outside the retention root is read

#### Scenario: A retained run is requested

- **WHEN** the run id names a directory inside the retention root
- **THEN** the server returns that run's `verdict.json`

#### Scenario: The run id is empty or absolute

- **WHEN** the run id is empty or an absolute path
- **THEN** the server rejects it before opening any file
