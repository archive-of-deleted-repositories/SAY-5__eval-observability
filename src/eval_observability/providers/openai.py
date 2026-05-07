"""OpenAI ChatProvider — thin wrapper, off the hot path in CI."""

from __future__ import annotations

import os
import time
from typing import Any

from .base import ChatMessage, ChatResponse


class OpenAIProvider:
    name = "openai"

    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key or os.environ.get("OPENAI_API_KEY")
        if not self._api_key:
            raise RuntimeError("OPENAI_API_KEY not set")

    def chat(
        self,
        messages: list[ChatMessage],
        *,
        model: str,
        max_tokens: int = 512,
        temperature: float = 0.0,
    ) -> ChatResponse:
        try:
            from openai import OpenAI  # type: ignore[import-not-found]
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("openai package not installed") from exc
        client = OpenAI(api_key=self._api_key)
        start = time.perf_counter()
        resp: Any = client.chat.completions.create(
            model=model,
            messages=[{"role": m.role, "content": m.content} for m in messages],
            max_tokens=max_tokens,
            temperature=temperature,
        )
        latency_ms = (time.perf_counter() - start) * 1000.0
        choice = resp.choices[0].message
        usage = resp.usage
        return ChatResponse(
            text=choice.content or "",
            model=model,
            tokens_in=getattr(usage, "prompt_tokens", 0),
            tokens_out=getattr(usage, "completion_tokens", 0),
            cost_usd=0.0,
            latency_ms=latency_ms,
            raw={"id": resp.id},
        )
