"""Welch's two-sample t-test (unequal variances).

Implemented in pure Python so the runtime has no scipy dependency. The unit
test suite asserts agreement with ``scipy.stats.ttest_ind(equal_var=False)``
to four decimal places.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class TTestResult:
    statistic: float
    p_value: float
    df: float
    mean_a: float
    mean_b: float


def _mean(xs: Sequence[float]) -> float:
    return sum(xs) / len(xs)


def _variance(xs: Sequence[float]) -> float:
    if len(xs) < 2:
        return 0.0
    m = _mean(xs)
    return sum((x - m) ** 2 for x in xs) / (len(xs) - 1)


def _lgamma(x: float) -> float:
    return math.lgamma(x)


def _betacf(a: float, b: float, x: float, max_iter: int = 200, eps: float = 1e-12) -> float:
    """Continued fraction for the regularized incomplete beta — Lentz's method."""
    qab = a + b
    qap = a + 1.0
    qam = a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < 1e-30:
        d = 1e-30
    d = 1.0 / d
    h = d
    for m in range(1, max_iter + 1):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < 1e-30:
            d = 1e-30
        c = 1.0 + aa / c
        if abs(c) < 1e-30:
            c = 1e-30
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < 1e-30:
            d = 1e-30
        c = 1.0 + aa / c
        if abs(c) < 1e-30:
            c = 1e-30
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < eps:
            break
    return h


def _betainc(a: float, b: float, x: float) -> float:
    """Regularized incomplete beta function I_x(a,b)."""
    if x < 0.0 or x > 1.0:
        raise ValueError("x must be in [0, 1]")
    if x == 0.0:
        return 0.0
    if x == 1.0:
        return 1.0
    bt = math.exp(
        _lgamma(a + b) - _lgamma(a) - _lgamma(b) + a * math.log(x) + b * math.log(1.0 - x)
    )
    if x < (a + 1.0) / (a + b + 2.0):
        return bt * _betacf(a, b, x) / a
    return 1.0 - bt * _betacf(b, a, 1.0 - x) / b


def _t_sf(t: float, df: float) -> float:
    """Survival function of Student's t distribution: P(T > t)."""
    x = df / (df + t * t)
    cdf_upper = 0.5 * _betainc(df / 2.0, 0.5, x)
    return cdf_upper if t > 0 else 1.0 - cdf_upper


def two_sided_t_p_value(t: float, df: float) -> float:
    return 2.0 * _t_sf(abs(t), df)


def welch_t_test(a: Sequence[float], b: Sequence[float]) -> TTestResult:
    """Welch's two-sample t-test with unequal variances.

    Compares samples ``a`` (current) against ``b`` (prior). The statistic is
    ``(mean_a - mean_b) / sqrt(var_a/n_a + var_b/n_b)`` and degrees of freedom
    are computed via the Welch-Satterthwaite equation. Returns the two-sided
    p-value.
    """
    if len(a) < 2 or len(b) < 2:
        raise ValueError("each sample must have at least 2 observations")
    n_a, n_b = len(a), len(b)
    mean_a, mean_b = _mean(a), _mean(b)
    var_a, var_b = _variance(a), _variance(b)
    se_sq = var_a / n_a + var_b / n_b
    if se_sq == 0.0:
        statistic = 0.0
        p_value = 1.0
        df = float(n_a + n_b - 2)
    else:
        statistic = (mean_a - mean_b) / math.sqrt(se_sq)
        df_num = se_sq**2
        df_den = (var_a / n_a) ** 2 / (n_a - 1) + (var_b / n_b) ** 2 / (n_b - 1)
        df = df_num / df_den if df_den > 0 else float(n_a + n_b - 2)
        p_value = two_sided_t_p_value(statistic, df)
    return TTestResult(statistic=statistic, p_value=p_value, df=df, mean_a=mean_a, mean_b=mean_b)
