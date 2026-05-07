"""Reasoning: multi-step word problems.

Gold = ``{"answer": str, "expected_steps": int}``. Final-answer exact match
plus a chain-of-thought presence flag.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from ._base import Example, ScoreResult

name = "reasoning"

_ANSWER_RE = re.compile(r"answer\s*[:=]\s*([^\n]+)", re.IGNORECASE)
_STEP_RE = re.compile(r"(step\s*\d+|working|let me)", re.IGNORECASE)


def load_suite(path: Path) -> list[Example]:
    raw = yaml.safe_load(path.read_text())
    out: list[Example] = []
    for item in raw["examples"]:
        out.append(
            Example(
                id=item["id"],
                category=name,
                input=item["input"],
                gold={
                    "answer": str(item["gold"]["answer"]),
                    "expected_steps": int(item["gold"].get("expected_steps", 1)),
                },
                metadata=item.get("metadata", {}),
            )
        )
    return out


def build_prompt(example: Example) -> str:
    return (
        "Solve the problem. Show your reasoning step by step, then write a "
        "final line of the form `Answer: <value>`.\n"
        f"[[example_id={example.id}]]\n"
        f"Problem: {example.input}"
    )


def _extract_answer(text: str) -> str:
    match = _ANSWER_RE.search(text)
    if not match:
        return text.strip().splitlines()[-1].strip() if text.strip() else ""
    return match.group(1).strip().rstrip(".")


def _has_chain_of_thought(text: str) -> bool:
    return bool(_STEP_RE.search(text))


def score(example: Example, output: str) -> ScoreResult:
    gold_ans = example.gold["answer"].strip().lower()
    pred_ans = _extract_answer(output).lower()
    correct = pred_ans == gold_ans
    has_cot = _has_chain_of_thought(output)
    final_score = 1.0 if (correct and has_cot) else (0.5 if correct else 0.0)
    return ScoreResult(
        score=final_score,
        passed=correct and has_cot,
        details={
            "predicted_answer": pred_ans,
            "gold_answer": gold_ans,
            "chain_of_thought": has_cot,
        },
    )
