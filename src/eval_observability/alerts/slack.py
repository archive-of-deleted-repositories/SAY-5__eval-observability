"""Slack incoming-webhook destination."""

from __future__ import annotations

from dataclasses import dataclass

from . import _http
from .base import Alert


@dataclass
class SlackDestination:
    """Post the alert as a simple ``text`` message to a Slack webhook URL."""

    webhook_url: str
    name: str = "slack"

    def send(self, alert: Alert) -> None:
        payload = {"text": f"*{alert.title}*\n{alert.summary}"}
        _http.post_json(self.webhook_url, payload)
