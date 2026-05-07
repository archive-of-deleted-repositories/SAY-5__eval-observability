"""Decision-table tests for the four scoring metrics."""

from __future__ import annotations

import pytest

from eval_observability.metrics.exact_match import exact_match
from eval_observability.metrics.f1 import entity_f1
from eval_observability.metrics.instruction_check import check_instruction
from eval_observability.metrics.rouge_l import rouge_l


@pytest.mark.parametrize(
    ("pred", "gold", "expected"),
    [
        ("yes", "yes", 1.0),
        ("Yes ", "yes", 1.0),
        ("no", "yes", 0.0),
        ("", "", 1.0),
        ("a", "", 0.0),
    ],
)
def test_exact_match(pred: str, gold: str, expected: float) -> None:
    assert exact_match(pred, gold) == expected


def test_entity_f1_perfect() -> None:
    p, r, f = entity_f1(["a", "b"], ["a", "b"])
    assert (p, r, f) == (1.0, 1.0, 1.0)


def test_entity_f1_partial() -> None:
    p, r, f = entity_f1(["a", "b", "c"], ["a", "b"])
    assert p == pytest.approx(2 / 3)
    assert r == pytest.approx(1.0)
    assert f == pytest.approx(0.8, rel=1e-6)


def test_entity_f1_disjoint() -> None:
    assert entity_f1(["x"], ["y"]) == (0.0, 0.0, 0.0)


def test_entity_f1_both_empty() -> None:
    assert entity_f1([], []) == (1.0, 1.0, 1.0)


def test_entity_f1_case_insensitive() -> None:
    _, _, f = entity_f1(["Paris"], ["paris"])
    assert f == 1.0


def test_rouge_l_identical() -> None:
    assert rouge_l("the quick brown fox", "the quick brown fox") == pytest.approx(1.0, abs=1e-6)


def test_rouge_l_disjoint() -> None:
    assert rouge_l("alpha beta", "gamma delta") == 0.0


def test_rouge_l_partial() -> None:
    score = rouge_l("the cat sat on the mat", "the cat is on the mat")
    assert 0.5 < score < 1.0


def test_rouge_l_empty() -> None:
    assert rouge_l("", "anything") == 0.0
    assert rouge_l("anything", "") == 0.0


def test_instruction_check_all_satisfied() -> None:
    out = '{"A": "x", "B": "One. Two. Three.", "C": 5}'
    spec = {
        "json_only": True,
        "required_keys": ["A", "B", "C"],
        "sentence_count": {"B": 3},
        "value_types": {"C": "int"},
    }
    res = check_instruction(out, spec)
    assert res["passed"] is True
    assert res["score"] == 1.0


def test_instruction_check_wrong_sentence_count() -> None:
    out = '{"A": "x", "B": "One. Two.", "C": 5}'
    spec = {
        "json_only": True,
        "required_keys": ["A", "B", "C"],
        "sentence_count": {"B": 3},
    }
    res = check_instruction(out, spec)
    assert res["passed"] is False
    assert 0 < res["score"] < 1


def test_instruction_check_invalid_json() -> None:
    res = check_instruction("not json", {"json_only": True})
    assert res["passed"] is False
    assert res["score"] == 0.0


def test_instruction_check_missing_key() -> None:
    out = '{"A": "x", "B": "One. Two. Three."}'
    spec = {"json_only": True, "required_keys": ["A", "B", "C"]}
    res = check_instruction(out, spec)
    assert res["passed"] is False
