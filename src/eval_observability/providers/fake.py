"""Deterministic FakeProvider used for hermetic CI runs.

The provider is keyed off ``sha256(messages + model)`` so the same input always
produces the same output. A small registry of canned answers covers the
six task categories. Some answers are intentionally wrong so eval scores are
not all 100% — that exercises the failure path of every metric.
"""

from __future__ import annotations

import hashlib
import json
import time
from typing import Any

from .base import ChatMessage, ChatResponse


def _hash_key(messages: list[ChatMessage], model: str) -> str:
    payload = json.dumps(
        {"model": model, "messages": [(m.role, m.content) for m in messages]},
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# Canned responses keyed by an "example_id" tag we embed in the user message.
# The runner adds a magic line `[[example_id=<id>]]` to the user prompt so the
# fake provider can route to the correct canned answer. Some are deliberately
# wrong (marked with comments) to keep scores realistic.
CANNED: dict[str, str] = {
    # extraction
    "extraction-1": '{"entities": ["Paris", "France", "Eiffel Tower"]}',
    "extraction-2": '{"entities": ["Apollo 11", "Neil Armstrong", "Buzz Aldrin", "Moon"]}',
    "extraction-3": '{"entities": ["Marie Curie", "radium", "polonium"]}',
    "extraction-4": '{"entities": ["Mount Everest", "Nepal", "Tibet"]}',
    # WRONG: missing "carbon"
    "extraction-5": '{"entities": ["graphite", "diamond"]}',
    "extraction-6": '{"entities": ["Pacific", "Atlantic", "Indian", "Arctic", "Southern"]}',
    "extraction-7": '{"entities": ["Shakespeare", "Hamlet", "Macbeth", "Othello"]}',
    "extraction-8": '{"entities": ["Pluto", "Charon"]}',
    # WRONG: hallucinates an extra entity
    "extraction-9": '{"entities": ["Saturn", "rings", "Titan", "Jupiter"]}',
    "extraction-10": '{"entities": ["Einstein", "relativity", "photoelectric"]}',
    # classification
    "classification-1": "positive",
    "classification-2": "negative",
    "classification-3": "neutral",
    "classification-4": "positive",
    "classification-5": "negative",
    # WRONG
    "classification-6": "positive",
    "classification-7": "negative",
    "classification-8": "neutral",
    "classification-9": "positive",
    # WRONG
    "classification-10": "neutral",
    # summarization
    "summarization-1": "Photosynthesis converts sunlight into chemical energy stored in glucose.",
    "summarization-2": "The mitochondria produce ATP through cellular respiration.",
    "summarization-3": "DNA encodes genetic information using four nucleotide bases.",
    "summarization-4": "Plate tectonics explains the movement of Earth's lithospheric plates.",
    "summarization-5": "The water cycle moves water through evaporation, condensation, and precipitation.",
    # WRONG: off-topic
    "summarization-6": "The capital of France is Paris.",
    "summarization-7": "Newton's laws describe the relationship between motion and forces.",
    "summarization-8": "Evolution by natural selection is driven by heritable variation and differential reproduction.",
    "summarization-9": "Antibiotics target bacterial cells while sparing host cells.",
    "summarization-10": "Black holes form when massive stars collapse under their own gravity.",
    # reasoning
    "reasoning-1": "Let me work step by step. 12 * 4 = 48. Then 48 + 7 = 55. Answer: 55",
    "reasoning-2": "Step 1: 100 - 37 = 63. Step 2: 63 / 9 = 7. Answer: 7",
    "reasoning-3": "Working: 5 ^ 3 = 125. Answer: 125",
    "reasoning-4": "I think the answer is 42",  # WRONG: no steps shown, wrong number
    "reasoning-5": "Step 1: 8 + 12 = 20. Step 2: 20 * 3 = 60. Answer: 60",
    "reasoning-6": "Working: 144 / 12 = 12. Answer: 12",
    "reasoning-7": "Step 1: 7 * 8 = 56. Answer: 56",
    "reasoning-8": "Step 1: 25 squared = 625. Answer: 625",
    "reasoning-9": "Step 1: 1000 - 250 = 750. Step 2: 750 / 5 = 150. Answer: 150",
    "reasoning-10": "Working: 9 * 9 = 81. Step 2: 81 + 19 = 100. Answer: 100",
    # code
    "code-1": "def add(a, b):\n    return a + b\n",
    "code-2": "def is_even(n):\n    return n % 2 == 0\n",
    "code-3": "def reverse_string(s):\n    return s[::-1]\n",
    "code-4": "def factorial(n):\n    if n <= 1:\n        return 1\n    return n * factorial(n - 1)\n",
    "code-5": "def max_of_list(xs):\n    return max(xs)\n",
    # WRONG: off-by-one
    "code-6": "def fib(n):\n    if n < 2:\n        return n\n    return fib(n - 1) + fib(n - 2) + 1\n",
    "code-7": "def count_vowels(s):\n    return sum(1 for c in s.lower() if c in 'aeiou')\n",
    "code-8": "def is_palindrome(s):\n    s = s.lower()\n    return s == s[::-1]\n",
    "code-9": "def gcd(a, b):\n    while b:\n        a, b = b, a % b\n    return a\n",
    # WRONG: returns wrong type
    "code-10": "def flatten(xs):\n    return str(xs)\n",
    # instruction_following
    "instruction_following-1": '{"A": "alpha", "B": "First sentence. Second sentence. Third sentence.", "C": 42}',
    "instruction_following-2": '{"A": "beta", "B": "One. Two. Three.", "C": 7}',
    "instruction_following-3": '{"A": "gamma", "B": "Start. Middle. End.", "C": 100}',
    # WRONG: missing key C
    "instruction_following-4": '{"A": "delta", "B": "Lorem. Ipsum. Dolor."}',
    "instruction_following-5": '{"A": "epsilon", "B": "Aa. Bb. Cc.", "C": 1}',
    # WRONG: 4 sentences instead of 3
    "instruction_following-6": '{"A": "zeta", "B": "One. Two. Three. Four.", "C": 12}',
    "instruction_following-7": '{"A": "eta", "B": "Cat. Dog. Bird.", "C": 3}',
    "instruction_following-8": '{"A": "theta", "B": "Red. Green. Blue.", "C": 9}',
    "instruction_following-9": '{"A": "iota", "B": "Sun. Moon. Star.", "C": 5}',
    "instruction_following-10": '{"A": "kappa", "B": "Yes. No. Maybe.", "C": 0}',
}

EXAMPLE_ID_MARKER = "[[example_id="


def _extract_example_id(messages: list[ChatMessage]) -> str | None:
    for msg in messages:
        idx = msg.content.find(EXAMPLE_ID_MARKER)
        if idx != -1:
            end = msg.content.find("]]", idx)
            if end != -1:
                return msg.content[idx + len(EXAMPLE_ID_MARKER) : end]
    return None


class FakeProvider:
    """Deterministic chat provider for hermetic CI runs."""

    name = "fake"

    def __init__(self, latency_ms: float = 5.0) -> None:
        self._latency_ms = latency_ms

    def chat(
        self,
        messages: list[ChatMessage],
        *,
        model: str,
        max_tokens: int = 512,
        temperature: float = 0.0,
    ) -> ChatResponse:
        start = time.perf_counter()
        example_id = _extract_example_id(messages)
        if example_id is not None and example_id in CANNED:
            text = CANNED[example_id]
        else:
            digest = _hash_key(messages, model)
            text = f"[[fake:{digest[:8]}]]"
        elapsed = (time.perf_counter() - start) * 1000.0 + self._latency_ms
        tokens_in = sum(len(m.content) for m in messages) // 4
        tokens_out = max(1, len(text) // 4)
        raw: dict[str, Any] = {"example_id": example_id, "deterministic": True}
        return ChatResponse(
            text=text,
            model=model,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost_usd=0.0,
            latency_ms=elapsed,
            raw=raw,
        )
