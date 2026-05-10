"""Settings parses ``EVAL_OBS_ALERTS`` as JSON into a destination config."""

from __future__ import annotations

import pytest

from eval_observability.alerts import (
    LogOnlyDestination,
    PagerDutyDestination,
    SlackDestination,
    WebhookDestination,
    build_destinations,
)
from eval_observability.settings import Settings


def test_alerts_default_is_empty_list(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("EVAL_OBS_ALERTS", raising=False)
    s = Settings()
    assert s.alerts == []
    [dest] = build_destinations(s.alerts)
    assert isinstance(dest, LogOnlyDestination)


def test_alerts_parses_json_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "EVAL_OBS_ALERTS",
        '[{"kind":"slack","webhook_url":"https://hooks.slack.com/x"},'
        '{"kind":"pagerduty","integration_key":"k"},'
        '{"kind":"webhook","url":"https://example.com/h"}]',
    )
    s = Settings()
    dests = build_destinations(s.alerts)
    assert len(dests) == 3
    assert isinstance(dests[0], SlackDestination)
    assert isinstance(dests[1], PagerDutyDestination)
    assert isinstance(dests[2], WebhookDestination)


def test_alerts_explicit_empty_list_resolves_to_log_only(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EVAL_OBS_ALERTS", "[]")
    s = Settings()
    assert s.alerts == []
    [dest] = build_destinations(s.alerts)
    assert isinstance(dest, LogOnlyDestination)
