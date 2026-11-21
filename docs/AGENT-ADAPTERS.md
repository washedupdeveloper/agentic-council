# Reviewer adapters

`council` is agent-agnostic at the reviewer seam. The review engine owns the
prompt, schema, proof execution and verdict; an adapter owns how one agent is
invoked for each sample.

Two adapters ship today: **Hermes** and **direct**, an OpenAI-compatible
endpoint. The other editors and agent CLIs are examples of the contract, not
shipped integrations. Add an adapter as a module
and list it in `src/council/agents/__init__.py`; no review-engine file should
need to know its name or command line.

## The interface

An adapter implements four attributes and three methods:

```python
class AgentAdapter(Protocol):
    name: str
    description: str
    profile_required: bool
    default_binary: str

    def runner(self, options: AgentOptions) -> Runner:
        """prompt -> raw agent answer"""

    def identity(self, options: AgentOptions) -> AgentIdentity:
        """the agent configuration that enters the instrument digest"""

    def available(self, options: AgentOptions) -> tuple[bool, str]:
        """whether the executable is present, and a human detail"""
```

`AgentOptions` is the deployment surface:

```python
AgentOptions(
    binary="...",       # executable override
    profile="...",      # adapter-specific profile, if it has one
    reasoning=None,     # optional effort
    stream=True,        # adapter may ignore it
    idle_timeout=120,
    timeout=900,
    sandbox=False,
)
```

`profile_required` is `True` for Hermes. A future adapter that uses no profile
must set it to `False`; the CLI still passes the value, and the adapter may
ignore it.

`AgentIdentity` is intentionally small:

```python
AgentIdentity(
    agent="hermes",
    profile="council-generalist",
    source="profiles/council-generalist/config.yaml",
    sha256="...",       # 16 hex characters, or empty when unknown
)
```

The digest includes the agent name and the identity hash. A changed command,
model, profile or adapter configuration must produce a different instrument.

## Adding an adapter

1. Add a module under `src/council/agents/`, for example `myagent.py`.
2. Implement the protocol. The runner must return the raw answer and must raise
   `ReviewerMissing` when the executable cannot start. Any other sample failure
   must raise `OSError`, which the existing retry path records.
3. Identify its configuration in `identity`. If the adapter has a profile file,
   hash its bytes; if it has none, hash the command/version facts that change
   the answer. An empty hash means "unknown", not "unchanged".
4. Implement `available`; do not make `council agents` guess a path.
5. Add one instance to `BUILTIN` in `src/council/agents/__init__.py`.
6. Add tests beside `tests/test_agents.py` using a fake adapter and the real
   review path. Test the selected agent, the command options, identity and the
   verdict record.

Minimal example, not shipped:

```python
from __future__ import annotations

import json
import shutil
import subprocess

from ..sample import ReviewerMissing, Runner
from .base import AgentIdentity, AgentOptions


class MyAgent:
    name = "myagent"
    description = "My agent's non-interactive reviewer"
    profile_required = False
    default_binary = "myagent"

    def runner(self, options: AgentOptions) -> Runner:
        def run(prompt: str) -> str:
            try:
                proc = subprocess.run(
                    [options.binary, "review", "-"],
                    input=prompt, capture_output=True, text=True,
                    timeout=options.timeout, check=False,
                )
            except (FileNotFoundError, PermissionError) as exc:
                raise ReviewerMissing(f"{options.binary!r} is not installed") from exc
            if proc.returncode != 0:
                raise OSError(f"{options.binary} exited {proc.returncode}")
            return proc.stdout
        return run

    def identity(self, options: AgentOptions) -> AgentIdentity:
        return AgentIdentity("myagent", source=options.binary, sha256="")

    def available(self, options: AgentOptions) -> tuple[bool, str]:
        path = shutil.which(options.binary)
        return (True, path) if path else (False, f"{options.binary} is not on PATH")
```

The example is deliberately not registered: a CLI whose contract has not been
verified against its real output is worse than no adapter.

## Rules the adapter must preserve

- **One process per sample.** Do not reuse a session or a running server; the
  existing sample retry, timeout and evidence trail assume one answer per call.
- **The prompt is data.** Pass it by stdin or a temporary file. Do not build a
  shell command from it.
- **The answer is data.** Return raw stdout; schema parsing, proof execution and
  retry remain in the review engine.
- **No engine imports.** An adapter may import `Runner`, `AgentOptions` and
  `AgentIdentity`; it must not import the prompt, proof or verdict internals.
- **No silent fallback.** A missing binary is `ReviewerMissing`; a non-zero exit,
  a timeout or an empty answer is `OSError`. Never return an empty string as a
  clean answer.
- **Read-only is the caller's policy.** Agents can edit the repository or run
  commands. Use the adapter's read-only mode and, where available, the existing
  bwrap sandbox; do not let a review write to the source tree.

## The direct adapter

`--agent direct` sends one Chat Completions request per sample, with no agent
process and no profile. It is for a deployment that has pinned a model on an
OpenAI-compatible endpoint and wants none of the agent boot cost.

| variable | default | meaning |
|---|---|---|
| `COUNCIL_DIRECT_BASE_URL` | `https://api.surplusintelligence.ai/v1` | endpoint root; `/chat/completions` is appended |
| `COUNCIL_DIRECT_MODEL` | — (required) | the model id sent in the request |
| `COUNCIL_DIRECT_API_KEY` | — (required) | bearer token; never written to the run record |
| `COUNCIL_DIRECT_MAX_TOKENS` | `8192` | response cap |

```sh
COUNCIL_DIRECT_MODEL=claude-fable-5.2 \
COUNCIL_DIRECT_API_KEY=... \
  council review --agent direct
```

The identity is a hash of the model, the endpoint and the prompt version. A key
change does not change the identity; a model or endpoint change does. The key
itself is not part of the identity and must not be logged.

The adapter raises `ReviewerMissing` when the configuration is absent, and
`OSError` for an HTTP error, a malformed response or an empty answer. It never
falls back to another model.

## Use it

```sh
council agents                     # adapter, availability and executable
council doctor --agent hermes      # probe the selected adapter
council review --agent hermes      # one review; default is already hermes
```

MCP and ACP use the same selection:

```sh
council-mcp --agent hermes
council-acp --agent hermes
```

The protocol adapters do not need to know which reviewer adapter is installed;
they pass `--agent` to the public CLI.

## Current boundary

Hermes and direct are in `BUILTIN`. The architecture is ready for Codex, Cursor,
DeepSeek Harness or another agent, but each needs its own adapter and a test of
its real non-interactive output. Do not add a generic "run any command" adapter
without deciding the prompt delivery, output format and read-only policy; those
are exactly the facts that differ between agents.

See [`M33.md`](M33.md) for the decision record and [`../tests/test_agents.py`](../tests/test_agents.py)
for the executable seam test. The host-agent skill is separate:
[`../skills/council/SKILL.md`](../skills/council/SKILL.md) teaches an editor
agent how to call the CLI; it is not a reviewer adapter.
