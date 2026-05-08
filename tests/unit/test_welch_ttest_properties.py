"""Hypothesis property tests for ``welch_t_test``.

The hand-rolled Welch's t-test implementation must satisfy three properties for
*any* input within the supported range:

1. **Agreement with scipy** within ``1e-4`` absolute tolerance on both the
   statistic and the p-value.
2. **Group-swap symmetry**: swapping ``a`` and ``b`` flips the sign of the
   statistic but leaves ``|t|``, ``df``, and ``p_value`` unchanged.
3. **p-value bounds**: ``0 <= p_value <= 1`` for every reachable input.
"""

from __future__ import annotations

import math

import pytest
from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st
from scipy import stats  # type: ignore[import-untyped]

from eval_observability.regression.stats import welch_t_test


def _sample(draw: st.DrawFn, n: int, mean: float, var: float) -> list[float]:
    """Draw ``n`` deterministic-ish points centered on ``mean`` with sample variance ``var``.

    We synthesize the sample directly rather than drawing iid Gaussian noise so
    that the per-call sample mean / variance match the strategy parameters
    exactly. This makes the test scope match the problem statement —
    "(n_a, mean_a, var_a, n_b, mean_b, var_b)" — without depending on a
    pseudo-random sampler inside the strategy.
    """
    if n < 2:
        raise ValueError("n must be >= 2")
    base = [draw(st.floats(min_value=-1.0, max_value=1.0)) for _ in range(n)]
    cur_mean = sum(base) / n
    centered = [x - cur_mean for x in base]
    cur_var = sum(x * x for x in centered) / (n - 1)
    scale = 0.0 if cur_var == 0.0 or var == 0.0 else math.sqrt(var / cur_var)
    return [mean + scale * x for x in centered]


@st.composite
def _ttest_inputs(
    draw: st.DrawFn,
) -> tuple[list[float], list[float]]:
    n_a = draw(st.integers(min_value=2, max_value=40))
    n_b = draw(st.integers(min_value=2, max_value=40))
    mean_a = draw(st.floats(min_value=-5.0, max_value=5.0))
    mean_b = draw(st.floats(min_value=-5.0, max_value=5.0))
    var_a = draw(st.floats(min_value=1e-4, max_value=2.0))
    var_b = draw(st.floats(min_value=1e-4, max_value=2.0))
    a = _sample(draw, n_a, mean_a, var_a)
    b = _sample(draw, n_b, mean_b, var_b)
    return a, b


@settings(max_examples=120, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(samples=_ttest_inputs())
def test_agreement_with_scipy_property(samples: tuple[list[float], list[float]]) -> None:
    a, b = samples
    sp = stats.ttest_ind(a, b, equal_var=False)
    if math.isnan(float(sp.statistic)) or math.isnan(float(sp.pvalue)):
        # scipy returns NaN when both samples have zero variance — assume away.
        assume(False)
    mine = welch_t_test(a, b)
    assert mine.statistic == pytest.approx(float(sp.statistic), abs=1e-4, rel=1e-4)
    assert mine.p_value == pytest.approx(float(sp.pvalue), abs=1e-4, rel=1e-4)


@settings(max_examples=120, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(samples=_ttest_inputs())
def test_group_swap_symmetry(samples: tuple[list[float], list[float]]) -> None:
    a, b = samples
    forward = welch_t_test(a, b)
    reverse = welch_t_test(b, a)
    # statistic flips sign, |t| / df / p stay equal
    assert forward.statistic == pytest.approx(-reverse.statistic, abs=1e-9)
    assert forward.df == pytest.approx(reverse.df, abs=1e-9)
    assert forward.p_value == pytest.approx(reverse.p_value, abs=1e-12)
    assert forward.mean_a == pytest.approx(reverse.mean_b, abs=1e-12)
    assert forward.mean_b == pytest.approx(reverse.mean_a, abs=1e-12)


@settings(max_examples=200, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(samples=_ttest_inputs())
def test_p_value_bounded(samples: tuple[list[float], list[float]]) -> None:
    a, b = samples
    res = welch_t_test(a, b)
    assert 0.0 <= res.p_value <= 1.0
    assert math.isfinite(res.p_value)
