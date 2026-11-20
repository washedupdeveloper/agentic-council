"""The reviewer-agent seam.

An adapter owns three things and nothing else: how one agent is started for a
sample, how its configuration is identified in the instrument digest, and
whether the executable is present. The review engine never imports an agent's
SDK or parses its CLI; it only calls the returned ``Runner``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ..sample import Runner


@dataclass(frozen=True, slots=True)
class AgentOptions:
    """Deployment values a CLI adapter may use to build its command."""

    binary: str = ""
    profile: str = ""
    reasoning: str | None = None
    stream: bool = True
    idle_timeout: int = 120
    timeout: int = 900
    sandbox: bool = False


@dataclass(frozen=True, slots=True)
class AgentIdentity:
    """The part of the instrument that names the agent and its configuration."""

    agent: str
    profile: str = ""
    source: str = ""
    sha256: str = ""


class AgentAdapter(Protocol):
    """One agent implementation. Add a module beside this one and list it in
    ``council.agents``; no review-engine code changes are needed."""

    name: str
    description: str
    profile_required: bool
    default_binary: str

    def runner(self, options: AgentOptions) -> Runner:
        """Return the prompt -> answer callable used for every sample."""
        ...

    def identity(self, options: AgentOptions) -> AgentIdentity:
        """Identify the agent configuration for the instrument digest."""
        ...

    def available(self, options: AgentOptions) -> tuple[bool, str]:
        """Whether the configured executable exists, and a human detail."""
        ...
