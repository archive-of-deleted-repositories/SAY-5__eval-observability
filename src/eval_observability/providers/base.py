"""ChatProvider Protocol, message and response shapes."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class ChatMessage:
    role: str
    content: str


@dataclass(frozen=True)
class ChatResponse:
    text: str
    model: str
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    latency_ms: float = 0.0
    raw: dict[str, object] = field(default_factory=dict)


@runtime_checkable
class ChatProvider(Protocol):
    name: str

    def chat(
        self,
        messages: list[ChatMessage],
        *,
        model: str,
        max_tokens: int = 512,
        temperature: float = 0.0,
    ) -> ChatResponse: ...
