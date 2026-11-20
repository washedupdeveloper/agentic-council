# Agent server

`council` can be used directly from an MCP host or from an ACP external agent.
The adapters are additive: they run the installed `council` command and consume
its public `--json` output and exit codes. They do not import the review engine,
and no existing V2 module or verdict contract changes.

## Install

### Python

```sh
pip install 'council[mcp,acp]'
```

The core wheel still has no runtime dependencies. `council[mcp]` installs only
the MCP SDK; `council[acp]` installs only the ACP SDK. The core package also
installs the two entry points; without the matching extra they exit 3 with the
install instruction rather than an import traceback.

### Nix

```sh
nix build .#council-mcp
nix build .#council-acp
nix build .#council-server     # both protocols
```

Each output contains `council`, `council-verify`, and the protocol command it
provides. To put the ACP command on a stable path for Zed:

```sh
nix profile install .#council-acp
# then use /home/<user>/.nix-profile/bin/council-acp
```

The plain `council` package has neither SDK in its closure.

## Server options

Both commands accept the same deployment options:

| option | meaning |
|---|---|
| `--repo-root DIR` | only repositories beneath this directory may be reviewed |
| `--state-root DIR` | where retained evidence is written; default is a per-user cache |
| `--agent NAME` | reviewer adapter; default is `hermes` |
| `--reviewer BIN` | executable for the selected adapter; default is the adapter's default |
| `--profile NAME` | profile for an adapter that uses one (Hermes) |
| `--no-sandbox` | pass `--no-sandbox` to council |
| `--timeout SECONDS` | whole review process timeout |
| `--council BIN` | council executable override; default is PATH, then `python -m council` |

The reviewer is a **server deployment choice**. It is not selected by an MCP
client. The host editor's model is not automatically available to the server;
council continues to use its configured reviewer. Host-model review would be a
separate contract and is not part of this adapter. See
[`AGENT-ADAPTERS.md`](AGENT-ADAPTERS.md) for the reviewer seam and how to add an
adapter.

## MCP

`council-mcp` is a local stdio MCP server with three tools:

```text
council_plan     units, prompt sizes and sample cost; no model call
council_review   run the gate and return verdict, findings and evidence
council_doctor   report git, reviewer, profile and sandbox checks
```

The complete verdict is retained under `--state-root` and exposed as the
resource `council://runs/<run_id>`; the tool result carries the run id and the
path.

### Zed Agent

Add a local MCP server in Zed's AI settings. The exact settings file depends on
the Zed install; the entry is equivalent to:

```json
{
  "context_servers": {
    "council": {
      "command": "council-mcp",
      "args": []
    }
  }
}
```

On Windows with council installed inside WSL, run the command through WSL and
give it the workspace path explicitly:

```json
{
  "context_servers": {
    "council": {
      "command": "wsl.exe",
      "args": [
        "-d", "NixOS", "--",
        "/home/nixolotl/.nix-profile/bin/council-mcp",
        "--repo-root", "C:\\Users\\Storm\\path\\to\\repo"
      ]
    }
  }
}
```

### VS Code and OpenCode

Use the same local stdio command in the host's MCP server configuration:

```text
command: council-mcp
args:    []
```

If the host runs on Windows and council is in WSL, use the `wsl.exe` form above.
The server does not require the host's model and does not use an editor
extension or an MCP remote transport.

## ACP

`council-acp` is a stdio ACP external agent. It supports:

```text
/plan       units, prompt sizes and sample cost
/review     run the review gate in the current workspace
/verdict    show the last verdict in this session
/help       commands and limits
```

The agent owns the reviewer configuration; it does not proxy review commands
through the editor's terminal or ask the editor to write files. The workspace
comes from the ACP session. A Windows workspace path is translated to `/mnt/...`
when the server runs under WSL.

### Zed Agent Panel

Add an external agent in Zed:

```json
{
  "agent_servers": {
    "council": {
      "type": "custom",
      "command": "council-acp",
      "args": []
    }
  }
}
```

On Windows with council in WSL:

```json
{
  "agent_servers": {
    "council": {
      "type": "custom",
      "command": "wsl.exe",
      "args": [
        "-d", "NixOS", "--",
        "/home/nixolotl/.nix-profile/bin/council-acp"
      ]
    }
  }
}
```

If Zed is already connected to the WSL project and runs the external agent in
that remote environment, use `council-acp` directly as `command`; the session
cwd is then the Linux workspace path. The server translates a Windows workspace
path to `/mnt/...` when it is launched through `wsl.exe` from a Windows client.

Open the Agent Panel, start a `council` thread, and type `/plan` or `/review`.
The thread is a review session, not a general chat agent.

## End-to-end proof

The protocol tests drive the official SDK clients against the actual adapters
and a real council CLI. The reviewer is a deterministic fake that emits one
`present` proof, so the test exercises the whole path without a model:

```sh
nix develop -c python -m pytest tests/test_server_cli.py \
  tests/test_mcp_server.py tests/test_acp_agent.py -q
```

The MCP test checks tool listing, plan output, a `FAIL` verdict through
`council_review`, evidence retention, doctor output and root refusal. The ACP
test checks `initialize`, `session/new`, `/plan`, `/review`, and the returned
gate verdict.

The Nix checks also include `server-mcp` and `server-acp` for import/help.

## Limits

- Local stdio only; there is no remote HTTP MCP transport, OAuth or multi-user
  serving.
- `council pr` and baseline commands are not exposed as server tools yet.
- The server does not edit code, post review comments or apply patches.
- ACP is an external-agent integration; it is not a VS Code extension.
- A missing optional SDK produces a clear install message, not a protocol
  startup traceback.
- The server writes evidence under `--state-root`, not into the reviewed
  repository.

## Related

- [`M32.md`](M32.md) — the decision record.
- [`../README.md`](../README.md) — the CLI and its exit codes.
