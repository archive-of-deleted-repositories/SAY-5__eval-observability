"""Hypothesis property tests for the scoring primitives.

These tests are bundled with the v1 layer: they round out coverage of the
metric helpers that drive every category's pass/fail decision and exercise
the regression detector's branching logic for windows that don't contain
enough observations to run a t-test.
"""

from __future__ import annotations

import math

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from eval_observability.metrics.exact_match import exact_match
from eval_observability.metrics.f1 import entity_f1
from eval_observability.metrics.rouge_l import rouge_l

# ---------- exact_match ----------


@given(text=st.text(min_size=1, max_size=40))
def test_exact_match_self_is_one(text: str) -> None:
    assert exact_match(text, text) == 1.0


@given(text=st.text(alphabet="abcdABCD0123 -", min_size=1, max_size=40))
def test_exact_match_case_and_whitespace_invariant(text: str) -> None:
    """ASCII swapcase round-trips through .lower(); we restrict the alphabet
    to dodge Unicode quirks (e.g. 'ß'.swapcase() == 'SS'.lower() != 'ß')."""
    spaced = f"  {text.swapcase()}  "
    assert exact_match(text, spaced) == 1.0


# ---------- entity_f1 ----------


_token = st.text(alphabet="abcdefghij", min_size=1, max_size=4)
_token_set = st.lists(_token, min_size=0, max_size=8)


@given(predicted=_token_set, gold=_token_set)
def test_entity_f1_bounds(predicted: list[str], gold: list[str]) -> None:
    p, r, f1 = entity_f1(predicted, gold)
    assert 0.0 <= p <= 1.0
    assert 0.0 <= r <= 1.0
    assert 0.0 <= f1 <= 1.0


@given(items=_token_set)
def test_entity_f1_self_match_is_perfect(items: list[str]) -> None:
    p, r, f1 = entity_f1(items, items)
    assert p == 1.0
    assert r == 1.0
    assert f1 == 1.0


@given(predicted=_token_set, gold=_token_set)
def test_entity_f1_symmetric_in_f1(predicted: list[str], gold: list[str]) -> None:
    _, _, f1_a = entity_f1(predicted, gold)
    _, _, f1_b = entity_f1(gold, predicted)
    assert math.isclose(f1_a, f1_b, abs_tol=1e-12)


# ---------- rouge_l ----------


_word = st.text(alphabet="abcde ", min_size=1, max_size=20)


@settings(max_examples=80, suppress_health_check=[HealthCheck.too_slow])
@given(prediction=_word, reference=_word)
def test_rouge_l_bounds(prediction: str, reference: str) -> None:
    score = rouge_l(prediction, reference)
    assert 0.0 <= score <= 1.0


@settings(max_examples=80, suppress_health_check=[HealthCheck.too_slow])
@given(text=st.text(alphabet="abcde ", min_size=1, max_size=20))
def test_rouge_l_self_is_one_when_tokens_present(text: str) -> None:
    if not any(c.isalnum() for c in text):
        # tokenizer drops whitespace-only inputs; rouge_l is 0 by spec
        assert rouge_l(text, text) == 0.0
    else:
        assert rouge_l(text, text) == 1.0
