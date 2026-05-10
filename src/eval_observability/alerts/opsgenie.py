"""Opsgenie Alert API destination."""

from __future__ import annotations

from dataclasses import dataclass

from . import _http
from .base import Alert

ALERTS_URL = "https://api.opsgenie.com/v2/alerts"


@dataclass
class OpsgenieDestination:
    """Open an Opsgenie alert via the Alert API. ``api_key`` must be a
    GenieKey-prefixed integration key.
    """

    api_key: str
    name: str = "opsgenie"
    priority: str = "P3"

    def send(self, alert: Alert) -> None:
        payload = {
            "message": alert.title,
            "alias": (
                f"eval-obs:{alert.suite_name}:{alert.suite_version}:"
                f"{alert.model_version}:{alert.category}"
            ),
            "description": alert.summary,
            "priority": self.priority,
            "details": {
                "model_version": alert.model_version,
                "delta": str(alert.delta),
                "p_value": str(alert.p_value),
                "current_mean": str(alert.current_mean),
                "prior_mean": str(alert.prior_mean),
                "detected_at": alert.detected_at,
            },
            "source": "eval-observability",
        }
        headers = {"Authorization": f"GenieKey {self.api_key}"}
        _http.post_json(ALERTS_URL, payload, headers=headers)
