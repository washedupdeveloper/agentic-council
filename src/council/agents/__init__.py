"""The adapter registry.

Only Hermes ships today. A new adapter is one module implementing
``AgentAdapter`` plus one entry in ``BUILTIN``; the CLI, the protocol servers and
the review engine all resolve agents through this table.
"""

from __future__ import annotations

from collections.abc import Iterable

from .base import AgentAdapter, AgentIdentity, AgentOptions
from .hermes import HermesAdapter

__all__ = [
    "AgentAdapter", "AgentIdentity", "AgentOptions", "AgentRegistry",
    "BUILTIN", "DEFAULT_AGENT", "DEFAULT_REGISTRY", "HermesAdapter",
    "register", "resolve", "unregister",
]

DEFAULT_AGENT = "hermes"

#: The shipped adapters. The tuple is deliberately explicit: a transport is not
#: safe to discover from an arbitrary import path without a review.
BUILTIN: tuple[AgentAdapter, ...] = (HermesAdapter(),)


class AgentRegistry:
    """A name-to-adapter table with a loud failure for an unknown name."""

    def __init__(self, adapters: Iterable[AgentAdapter] = ()) -> None:
        self._adapters: dict[str, AgentAdapter] = {}
        for adapter in adapters:
            self.register(adapter)

    def register(self, adapter: AgentAdapter) -> None:
        if not adapter.name:
            raise ValueError("reviewer agent name must not be empty")
        if adapter.name in self._adapters:
            raise ValueError(f"reviewer agent {adapter.name!r} is already registered")
        self._adapters[adapter.name] = adapter

    def unregister(self, name: str) -> None:
        """Remove an adapter; useful for an embedding test, not for a review."""
        self._adapters.pop(name, None)

    def get(self, name: str) -> AgentAdapter:
        try:
            return self._adapters[name]
        except KeyError as exc:
            available = ", ".join(sorted(self._adapters)) or "none"
            raise ValueError(
                f"unknown reviewer agent {name!r}; available: {available}"
            ) from exc

    def all(self) -> tuple[AgentAdapter, ...]:
        return tuple(self._adapters.values())


DEFAULT_REGISTRY = AgentRegistry(BUILTIN)


def resolve(name: str) -> AgentAdapter:
    """The adapter selected by a CLI flag or a server deployment option."""
    return DEFAULT_REGISTRY.get(name)


def register(adapter: AgentAdapter) -> None:
    """Add an adapter to this process; a CLI build normally adds it to BUILTIN."""
    DEFAULT_REGISTRY.register(adapter)


def unregister(name: str) -> None:
    """Remove a runtime adapter; useful to an embedding test."""
    DEFAULT_REGISTRY.unregister(name)
