"""Generic HTTP webhook destination."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from . import _http
from .base import Alert


@dataclass
class WebhookDestination:
    """POST the alert as JSON to ``url`` with optional extra ``headers``.

    The body has the shape::

        {"alert": <Alert as dict>, "title": "...", "summary": "..."}
    """

    url: str
    headers: dict[str, str] = field(default_factory=dict)
    name: str = "webhook"

    def send(self, alert: Alert) -> None:
        payload: dict[str, Any] = {
            "title": alert.title,
            "summary": alert.summary,
            "alert": {
                "suite_name": alert.suite_name,
                "suite_version": alert.suite_version,
                "model_version": alert.model_version,
                "category": alert.category,
                "delta": alert.delta,
                "p_value": alert.p_value,
                "current_mean": alert.current_mean,
                "prior_mean": alert.prior_mean,
                "detected_at": alert.detected_at,
                "extra": alert.extra,
            },
        }
        _http.post_json(self.url, payload, headers=self.headers)
