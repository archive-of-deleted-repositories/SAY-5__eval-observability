"""Extraction: pull a list of entities from a passage.

Gold = ``{"entities": [str, ...]}``. Score = entity-set F1.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from ..metrics.f1 import entity_f1
from ._base import Example, ScoreResult

name = "extraction"


def load_suite(path: Path) -> list[Example]:
    raw = yaml.safe_load(path.read_text())
    out: list[Example] = []
    for item in raw["examples"]:
        out.append(
            Example(
                id=item["id"],
                category=name,
                input=item["input"],
                gold={"entities": item["gold"]["entities"]},
                metadata=item.get("metadata", {}),
            )
        )
    return out


def build_prompt(example: Example) -> str:
    return (
        "Extract the named entities from the passage. "
        'Return JSON with shape {"entities": [...]}.\n\n'
        f"[[example_id={example.id}]]\n"
        f"Passage: {example.input}"
    )


def _parse_entities(output: str) -> list[str]:
    try:
        parsed: Any = json.loads(output)
    except (ValueError, TypeError):
        return []
    if isinstance(parsed, dict) and isinstance(parsed.get("entities"), list):
        return [str(x) for x in parsed["entities"]]
    return []


def score(example: Example, output: str) -> ScoreResult:
    pred = _parse_entities(output)
    gold = example.gold["entities"]
    precision, recall, f1 = entity_f1(pred, gold)
    return ScoreResult(
        score=f1,
        passed=f1 >= 0.999,
        details={"precision": precision, "recall": recall, "predicted": pred, "gold": gold},
    )
