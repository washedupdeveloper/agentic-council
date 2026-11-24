# Proposal

## Why

The Astra review found two release-blocking classes in the shipped boundary: the
composite action manifest is invalid YAML, and the proof engine refuted true
findings when a proof failed for an infrastructure reason (a missing module, or a
line reference that had drifted by one). A gate that can suppress a true
critical finding is not a gate. Several smaller failures share the same shape:
a guarantee is described, but a proxy is measured instead of the artifact.

## What Changes

- **Action manifest:** quote the `samples` description so the file is valid YAML;
  pass every action input through `env:` rather than interpolating it into Bash
  source; stop adding the private venv to `GITHUB_PATH`; call the installed
  binary by absolute path.
- **Proof adjudication:** a `repro` / `command` whose output shows a missing
  proof dependency is `UNRUNNABLE`, never `REFUTED`; a `present` quote found at a
  different line is `UNRUNNABLE` and names the real line; `python` is normalised
  to `python3` when the latter is the allowed interpreter.
- **Repository rules:** refuse a review whose rule documents are changed by the
  change under review unless the caller explicitly allows that change.
- **Proof sandbox:** mask `/home` and `/root` with a private tmpfs so a proof
  cannot read user-readable files outside the repository; bind a repository under
  `/tmp` after the private tmpfs rather than over it.
- **Milestone runner:** run acceptance predicates under the worker's guarded PATH;
  keep every predicate when a verify list mixes quoted and unquoted commands;
  do not treat a `#` inside a quoted value as a comment.
- **Mutation checker:** prove the unmodified suite is green before scoring any
  mutation.
- **MCP retention:** reject a run id that resolves outside the retention root.
- **Container tooling:** create a unique image workspace and refuse an unowned
  path; read an OCI index as well as Docker's manifest; extract layers with a
  containment check and handle whiteouts.

## Capabilities

### New Capabilities

- `mcp-resources`: retained verdict resources are addressable only inside the
  configured retention root.

### Modified Capabilities

- `review-reliability`: proof infrastructure failures and stale line references
  cannot become `refuted`; repository rules cannot be changed by the reviewed
  change; the command sandbox keeps user home paths out of view.
- `delivery-gate`: the shipped action manifest is parsed and checked; container
  tooling owns its workspace and handles OCI layouts.
- `milestone-runner`: predicates run under the guarded PATH and the task parser
  preserves every predicate.

## Impact

- `.github/actions/council/action.yml`, `.github/workflows/council.yml`
- `src/council/proofs.py`, `src/council/prepare.py`, `src/council/request.py`,
  `src/council/cli.py`, `src/council/cli_parser.py`
- `src/council/domain/sandbox.py`, `tools/sandbox.sh`
- `tools/milestone.py`, `tools/mutation_check.py`, `tools/image-run.sh`,
  `tools/materialise-image.sh`, `src/council_mcp/server.py`
- `tests/test_governance.py`, `tests/test_proofs.py`,
  `tests/test_domain_kernel.py`, `tests/test_milestone.py`,
  `tests/test_mcp_server.py`, `tests/test_sandbox_script.py`
- `pyproject.toml`, `flake.nix` (PyYAML in the test environment)