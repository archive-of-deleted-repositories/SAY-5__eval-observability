"""Provider registry — maps a provider name to a ChatProvider instance."""

from __future__ import annotations

from .base import ChatProvider
from .fake import FakeProvider


def get_provider(name: str) -> ChatProvider:
    name = name.lower()
    if name == "fake":
        return FakeProvider()
    if name == "openai":
        from .openai import OpenAIProvider

        return OpenAIProvider()
    if name == "anthropic":
        from .anthropic import AnthropicProvider

        return AnthropicProvider()
    raise ValueError(f"unknown provider: {name}")
