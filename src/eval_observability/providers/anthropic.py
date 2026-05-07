"""Anthropic ChatProvider — thin wrapper, off the hot path in CI."""

from __future__ import annotations

import os
import time
from typing import Any

from .base import ChatMessage, ChatResponse


class AnthropicProvider:
    name = "anthropic"

    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not self._api_key:
            raise RuntimeError("ANTHROPIC_API_KEY not set")

    def chat(
        self,
        messages: list[ChatMessage],
        *,
        model: str,
        max_tokens: int = 512,
        temperature: float = 0.0,
    ) -> ChatResponse:
        try:
            from anthropic import Anthropic  # type: ignore[import-not-found]
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("anthropic package not installed") from exc
        client = Anthropic(api_key=self._api_key)
        start = time.perf_counter()
        sys_msgs = [m.content for m in messages if m.role == "system"]
        chat_msgs = [{"role": m.role, "content": m.content} for m in messages if m.role != "system"]
        resp: Any = client.messages.create(
            model=model,
            system="\n".join(sys_msgs) or None,
            messages=chat_msgs,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        latency_ms = (time.perf_counter() - start) * 1000.0
        text = "".join(block.text for block in resp.content if hasattr(block, "text"))
        usage = resp.usage
        return ChatResponse(
            text=text,
            model=model,
            tokens_in=getattr(usage, "input_tokens", 0),
            tokens_out=getattr(usage, "output_tokens", 0),
            cost_usd=0.0,
            latency_ms=latency_ms,
            raw={"id": resp.id},
        )
