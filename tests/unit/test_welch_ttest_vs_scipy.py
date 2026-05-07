"""Welch's t-test must agree with ``scipy.stats.ttest_ind(equal_var=False)``."""

from __future__ import annotations

import random

import pytest
from scipy import stats  # type: ignore[import-untyped]

from eval_observability.regression.stats import welch_t_test


@pytest.mark.parametrize("seed", list(range(20)))
def test_agreement_with_scipy(seed: int) -> None:
    rng = random.Random(seed)
    n_a = rng.randint(5, 30)
    n_b = rng.randint(5, 30)
    mu_a = rng.uniform(0.6, 0.95)
    mu_b = rng.uniform(0.6, 0.95)
    sigma_a = rng.uniform(0.02, 0.1)
    sigma_b = rng.uniform(0.02, 0.1)
    a = [rng.gauss(mu_a, sigma_a) for _ in range(n_a)]
    b = [rng.gauss(mu_b, sigma_b) for _ in range(n_b)]

    sp = stats.ttest_ind(a, b, equal_var=False)
    mine = welch_t_test(a, b)

    assert mine.statistic == pytest.approx(float(sp.statistic), abs=1e-4)
    assert mine.p_value == pytest.approx(float(sp.pvalue), abs=1e-4)


def test_zero_variance_returns_p_one() -> None:
    same = [0.5] * 10
    res = welch_t_test(same, list(same))
    assert res.statistic == 0.0
    assert res.p_value == 1.0


def test_too_few_observations_raises() -> None:
    with pytest.raises(ValueError):
        welch_t_test([0.5], [0.5, 0.6])
