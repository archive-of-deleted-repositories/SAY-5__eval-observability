"""Per-category scoring decision tables."""

from __future__ import annotations

from pathlib import Path

import pytest

from eval_observability.categories import (
    classification,
    code,
    extraction,
    instruction_following,
    reasoning,
    summarization,
)
from eval_observability.categories._base import Example

SUITE = Path("eval/suites/core_v1")


def test_extraction_loads_ten_examples() -> None:
    items = extraction.load_suite(SUITE / "extraction.yaml")
    assert len(items) == 10
    assert items[0].category == "extraction"


def test_extraction_score_perfect() -> None:
    ex = Example(
        id="ex",
        category="extraction",
        input="x",
        gold={"entities": ["A", "B"]},
    )
    res = extraction.score(ex, '{"entities": ["a", "b"]}')
    assert res.passed is True


def test_extraction_score_partial() -> None:
    ex = Example(
        id="ex",
        category="extraction",
        input="x",
        gold={"entities": ["A", "B", "C"]},
    )
    res = extraction.score(ex, '{"entities": ["a"]}')
    assert res.passed is False
    assert 0 < res.score < 1


def test_classification_loads_ten_examples() -> None:
    items = classification.load_suite(SUITE / "classification.yaml")
    assert len(items) == 10
    assert "positive" in items[0].gold["labels"]


def test_classification_score() -> None:
    ex = Example(
        id="ex",
        category="classification",
        input="x",
        gold={"label": "positive", "labels": ["positive", "negative", "neutral"]},
    )
    assert classification.score(ex, "positive").passed is True
    assert classification.score(ex, "negative").passed is False


def test_summarization_score_high() -> None:
    ex = Example(
        id="ex",
        category="summarization",
        input="x",
        gold={"reference": "the quick brown fox jumps over the lazy dog"},
    )
    assert summarization.score(ex, "the quick brown fox jumps over the lazy dog").passed is True


def test_summarization_score_zero() -> None:
    ex = Example(
        id="ex",
        category="summarization",
        input="x",
        gold={"reference": "alpha beta gamma"},
    )
    res = summarization.score(ex, "completely unrelated text")
    assert res.passed is False
    assert res.score == 0.0


def test_reasoning_score_correct_with_steps() -> None:
    ex = Example(
        id="ex",
        category="reasoning",
        input="x",
        gold={"answer": "42", "expected_steps": 1},
    )
    res = reasoning.score(ex, "Step 1: ... Answer: 42")
    assert res.passed is True
    assert res.score == 1.0


def test_reasoning_score_correct_without_steps() -> None:
    ex = Example(
        id="ex",
        category="reasoning",
        input="x",
        gold={"answer": "42", "expected_steps": 1},
    )
    res = reasoning.score(ex, "Answer: 42")
    assert res.passed is False
    assert res.score == 0.5


def test_reasoning_score_wrong_answer() -> None:
    ex = Example(
        id="ex",
        category="reasoning",
        input="x",
        gold={"answer": "42", "expected_steps": 1},
    )
    res = reasoning.score(ex, "Step 1: ... Answer: 41")
    assert res.passed is False
    assert res.score == 0.0


def test_code_score_passes() -> None:
    tests = "def test():\n    assert add(1, 2) == 3\n"
    ex = Example(
        id="ex",
        category="code",
        input="def add(a, b):",
        gold={"function_name": "add", "tests": tests},
    )
    res = code.score(ex, "def add(a, b):\n    return a + b\n")
    assert res.passed is True
    assert res.score == 1.0


def test_code_score_fails() -> None:
    tests = "def test():\n    assert add(1, 2) == 3\n"
    ex = Example(
        id="ex",
        category="code",
        input="def add(a, b):",
        gold={"function_name": "add", "tests": tests},
    )
    res = code.score(ex, "def add(a, b):\n    return a - b\n")
    assert res.passed is False
    assert res.score == 0.0


def test_instruction_following_score() -> None:
    ex = Example(
        id="ex",
        category="instruction_following",
        input="x",
        gold={
            "json_only": True,
            "required_keys": ["A", "B"],
            "sentence_count": {"B": 2},
        },
    )
    good = '{"A": "x", "B": "One. Two."}'
    bad = '{"A": "x", "B": "Only one."}'
    assert instruction_following.score(ex, good).passed is True
    assert instruction_following.score(ex, bad).passed is False


@pytest.mark.parametrize(
    "module",
    [extraction, classification, summarization, reasoning, code, instruction_following],
)
def test_each_suite_has_ten_examples(module: object) -> None:
    path = SUITE / f"{module.name}.yaml"  # type: ignore[attr-defined]
    items = module.load_suite(path)  # type: ignore[attr-defined]
    assert len(items) == 10
