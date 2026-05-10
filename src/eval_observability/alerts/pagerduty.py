"""PagerDuty Events API v2 destination."""

from __future__ import annotations

from dataclasses import dataclass

from . import _http
from .base import Alert

EVENTS_URL = "https://events.pagerduty.com/v2/enqueue"


@dataclass
class PagerDutyDestination:
    """Trigger a PagerDuty event using an integration key (Events API v2)."""

    integration_key: str
    name: str = "pagerduty"
    severity: str = "warning"

    def send(self, alert: Alert) -> None:
        payload = {
            "routing_key": self.integration_key,
            "event_action": "trigger",
            "dedup_key": (
                f"eval-obs:{alert.suite_name}:{alert.suite_version}:"
                f"{alert.model_version}:{alert.category}"
            ),
            "payload": {
                "summary": alert.summary,
                "source": "eval-observability",
                "severity": self.severity,
                "component": alert.category,
                "group": alert.suite_name,
                "custom_details": {
                    "model_version": alert.model_version,
                    "delta": alert.delta,
                    "p_value": alert.p_value,
                    "current_mean": alert.current_mean,
                    "prior_mean": alert.prior_mean,
                    "detected_at": alert.detected_at,
                },
            },
        }
        _http.post_json(EVENTS_URL, payload)
