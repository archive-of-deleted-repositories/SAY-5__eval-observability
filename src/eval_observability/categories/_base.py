"""Common types for category modules."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol


@dataclass(frozen=True)
class Example:
    id: str
    category: str
    input: str
    gold: Any
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ScoreResult:
    score: float
    passed: bool
    details: dict[str, Any] = field(default_factory=dict)


class CategoryModule(Protocol):
    name: str

    def load_suite(self, path: Path) -> list[Example]: ...

    def build_prompt(self, example: Example) -> str: ...

    def score(self, example: Example, output: str) -> ScoreResult: ...
