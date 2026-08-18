"""Provider contracts for the NeuraHive core.

Implementations belong to adapters or consuming projects. These protocols keep
provider-specific SDKs and platform persistence outside the core package.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol, Sequence


@dataclass(frozen=True)
class Model:
    """Provider-neutral model descriptor."""

    provider: str
    model_id: str
    capabilities: frozenset[str] = frozenset()
    metadata: Mapping[str, Any] | None = None


class ModelProvider(Protocol):
    """Contract for an LLM/model adapter."""

    def get_model(self, model_id: str | None = None) -> Model: ...

    async def generate(
        self,
        *,
        model: Model,
        messages: Sequence[Mapping[str, Any]],
        tools: Sequence[Mapping[str, Any]] = (),
        **kwargs: Any,
    ) -> Any: ...


class MemoryProvider(Protocol):
    """Contract for short/long-term memory adapters."""

    async def remember(self, key: str, value: Any, *, namespace: str = "default") -> None: ...

    async def recall(self, key: str, *, namespace: str = "default") -> Any | None: ...

    async def search(self, query: str, *, namespace: str = "default", limit: int = 10) -> list[Any]: ...

    async def forget(self, key: str, *, namespace: str = "default") -> None: ...
