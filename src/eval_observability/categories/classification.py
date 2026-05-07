"""Classification: pick one label from a closed enum.

Gold = ``{"label": str, "labels": [str, ...]}``. Score = exact-match accuracy.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from ..metrics.exact_match import exact_match
from ._base import Example, ScoreResult

name = "classification"


def load_suite(path: Path) -> list[Example]:
    raw = yaml.safe_load(path.read_text())
    out: list[Example] = []
    labels: list[str] = list(raw.get("labels", []))
    for item in raw["examples"]:
        out.append(
            Example(
                id=item["id"],
                category=name,
                input=item["input"],
                gold={"label": item["gold"], "labels": labels},
                metadata=item.get("metadata", {}),
            )
        )
    return out


def build_prompt(example: Example) -> str:
    labels = ", ".join(example.gold["labels"])
    return (
        f"Classify the text into exactly one of: {labels}. "
        "Reply with only the label, lowercase.\n"
        f"[[example_id={example.id}]]\n"
        f"Text: {example.input}"
    )


def score(example: Example, output: str) -> ScoreResult:
    sc = exact_match(output, example.gold["label"])
    return ScoreResult(
        score=sc,
        passed=sc == 1.0,
        details={"prediction": output.strip().lower(), "gold": example.gold["label"]},
    )
