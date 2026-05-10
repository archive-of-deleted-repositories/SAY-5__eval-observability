"""Per-destination tests using a mocked HTTP client.

Each HTTP-based destination must:
  * call the right URL
  * include the right Authorization headers (where applicable)
  * include the alert's structural fields somewhere in the JSON body
"""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from eval_observability.alerts import (
    Alert,
    LogOnlyDestination,
    OpsgenieDestination,
    PagerDutyDestination,
    SlackDestination,
    WebhookDestination,
)
from eval_observability.alerts.opsgenie import ALERTS_URL as OPSGENIE_URL
from eval_observability.alerts.pagerduty import EVENTS_URL as PAGERDUTY_URL


@pytest.fixture()
def alert() -> Alert:
    return Alert(
        suite_name="core_v1",
        suite_version="core_v1",
        model_version="fake-large",
        category="extraction",
        delta=-0.04,
        p_value=0.0123,
        current_mean=0.81,
        prior_mean=0.85,
        detected_at="2026-05-08T00:00:00+00:00",
    )


def test_log_only_writes_to_stdout(alert: Alert, capsys: pytest.CaptureFixture[str]) -> None:
    LogOnlyDestination().send(alert)
    captured = capsys.readouterr()
    assert "ALERT" in captured.out
    assert "extraction" in captured.out


def test_slack_destination_posts_to_webhook(alert: Alert) -> None:
    with patch("eval_observability.alerts.slack._http.post_json") as mock_post:
        mock_post.return_value = (200, "ok")
        SlackDestination(webhook_url="https://hooks.slack.com/services/T/B/X").send(alert)
    assert mock_post.call_count == 1
    args, kwargs = mock_post.call_args
    assert args[0] == "https://hooks.slack.com/services/T/B/X"
    assert "extraction" in args[1]["text"]


def test_pagerduty_destination_uses_events_v2(alert: Alert) -> None:
    with patch("eval_observability.alerts.pagerduty._http.post_json") as mock_post:
        mock_post.return_value = (202, '{"status":"success"}')
        PagerDutyDestination(integration_key="abc123").send(alert)
    args, kwargs = mock_post.call_args
    assert args[0] == PAGERDUTY_URL
    payload = args[1]
    assert payload["routing_key"] == "abc123"
    assert payload["event_action"] == "trigger"
    assert payload["payload"]["component"] == "extraction"


def test_opsgenie_destination_sets_geniekey_header(alert: Alert) -> None:
    with patch("eval_observability.alerts.opsgenie._http.post_json") as mock_post:
        mock_post.return_value = (202, '{"requestId":"x"}')
        OpsgenieDestination(api_key="my-key").send(alert)
    args, kwargs = mock_post.call_args
    assert args[0] == OPSGENIE_URL
    assert kwargs["headers"] == {"Authorization": "GenieKey my-key"}
    assert "extraction" in json.dumps(args[1])


def test_webhook_destination_posts_alert_envelope(alert: Alert) -> None:
    with patch("eval_observability.alerts.webhook._http.post_json") as mock_post:
        mock_post.return_value = (200, "")
        WebhookDestination(
            url="https://example.com/hook",
            headers={"X-Token": "tok"},
        ).send(alert)
    args, kwargs = mock_post.call_args
    assert args[0] == "https://example.com/hook"
    assert kwargs["headers"] == {"X-Token": "tok"}
    body = args[1]
    assert body["alert"]["category"] == "extraction"
    assert body["alert"]["delta"] == pytest.approx(-0.04)


def test_post_json_serialises_body() -> None:
    """The stdlib helper must JSON-encode the body and set Content-Type."""
    from eval_observability.alerts._http import post_json

    captured: dict[str, object] = {}

    class _FakeResp:
        status = 200

        def __enter__(self) -> _FakeResp:  # noqa: PYI034
            return self

        def __exit__(self, *exc: object) -> None:
            return None

        def read(self) -> bytes:
            return b""

    def _fake_urlopen(req, timeout):  # noqa: ANN001
        captured["data"] = req.data
        captured["headers"] = dict(req.header_items())
        captured["url"] = req.full_url
        captured["method"] = req.get_method()
        return _FakeResp()

    with patch("eval_observability.alerts._http.urllib.request.urlopen", side_effect=_fake_urlopen):
        status, body = post_json("https://example.com/x", {"hello": 1}, headers={"X-A": "B"})
    assert status == 200
    assert json.loads(captured["data"]) == {"hello": 1}
    assert captured["method"] == "POST"
    # Header keys are case-normalised by urllib but the value pair is preserved.
    flat = {k.lower(): v for k, v in captured["headers"].items()}
    assert flat["content-type"] == "application/json"
    assert flat["x-a"] == "B"
