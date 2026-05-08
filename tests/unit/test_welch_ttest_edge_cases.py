"""Edge cases for the Welch / Student-t numerical helpers and the provider
registry.

These cover error paths and degenerate inputs that the property-based tests
don't reach (out-of-domain ``x`` for the regularized incomplete beta, the
``x in {0, 1}`` short-circuits, etc.) plus the lazy-imported provider
factory branches.
"""

from __future__ import annotations

import pytest

from eval_observability.providers import registry
from eval_observability.providers.fake import FakeProvider
from eval_observability.regression.stats import (
    _betainc,
    _variance,
    two_sided_t_p_value,
)


def test_variance_short_sample_returns_zero() -> None:
    assert _variance([0.5]) == 0.0
    assert _variance([]) == 0.0


def test_betainc_x_zero() -> None:
    assert _betainc(2.0, 3.0, 0.0) == 0.0


def test_betainc_x_one() -> None:
    assert _betainc(2.0, 3.0, 1.0) == 1.0


def test_betainc_x_out_of_domain() -> None:
    with pytest.raises(ValueError):
        _betainc(2.0, 3.0, -0.1)
    with pytest.raises(ValueError):
        _betainc(2.0, 3.0, 1.1)


def test_two_sided_p_value_negative_t() -> None:
    p_pos = two_sided_t_p_value(2.0, 10.0)
    p_neg = two_sided_t_p_value(-2.0, 10.0)
    assert p_pos == pytest.approx(p_neg, abs=1e-12)
    assert 0.0 < p_pos < 1.0


def test_two_sided_p_value_zero_statistic() -> None:
    assert two_sided_t_p_value(0.0, 10.0) == pytest.approx(1.0, abs=1e-9)


def test_registry_returns_fake() -> None:
    assert isinstance(registry.get_provider("fake"), FakeProvider)
    assert isinstance(registry.get_provider("FAKE"), FakeProvider)


def test_registry_unknown_provider_raises() -> None:
    with pytest.raises(ValueError, match="unknown provider"):
        registry.get_provider("nonsense")


def test_registry_lazy_imports_openai_and_anthropic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify the lazy-import branches resolve and instantiate when the
    expected API-key envs are present. The dummy key value is enough — we
    never make a real network call here.
    """
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    openai_provider = registry.get_provider("openai")
    anthropic_provider = registry.get_provider("anthropic")
    assert openai_provider.__class__.__name__ == "OpenAIProvider"
    assert anthropic_provider.__class__.__name__ == "AnthropicProvider"
