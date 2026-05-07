"""Summarization: produce a 1-2 sentence summary.

Gold = the reference summary. Score = ROUGE-L F-measure.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from ..metrics.rouge_l import rouge_l
from ._base import Example, ScoreResult

name = "summarization"
PASS_THRESHOLD = 0.5


def load_suite(path: Path) -> list[Example]:
    raw = yaml.safe_load(path.read_text())
    out: list[Example] = []
    for item in raw["examples"]:
        out.append(
            Example(
                id=item["id"],
                category=name,
                input=item["input"],
                gold={"reference": item["gold"]},
                metadata=item.get("metadata", {}),
            )
        )
    return out


def build_prompt(example: Example) -> str:
    return (
        "Summarize the passage in one or two sentences. Reply with the summary only.\n"
        f"[[example_id={example.id}]]\n"
        f"Passage: {example.input}"
    )


def score(example: Example, output: str) -> ScoreResult:
    reference = example.gold["reference"]
    sc = rouge_l(output, reference)
    return ScoreResult(
        score=sc,
        passed=sc >= PASS_THRESHOLD,
        details={"reference": reference, "rouge_l": sc},
    )
