"""Build :class:`AlertDestination` instances from a config list.

The config has the shape::

    [
        {"kind": "slack", "webhook_url": "https://hooks.slack.com/..."},
        {"kind": "pagerduty", "integration_key": "..."},
        {"kind": "webhook", "url": "https://example.com/hook"},
        {"kind": "log_only"},
    ]

Unknown ``kind`` values raise :class:`ValueError`. Missing required keys
raise :class:`TypeError` from the destination's ``__init__``.
"""

from __future__ import annotations

from typing import Any

from .base import AlertDestination
from .log_only import LogOnlyDestination
from .opsgenie import OpsgenieDestination
from .pagerduty import PagerDutyDestination
from .slack import SlackDestination
from .webhook import WebhookDestination


def build_destinations(config: list[dict[str, Any]] | None) -> list[AlertDestination]:
    """Materialize the config into a list of destinations.

    ``None`` or an empty list resolves to a single
    :class:`LogOnlyDestination` so the cron always has somewhere to send.
    """
    if not config:
        return [LogOnlyDestination()]

    out: list[AlertDestination] = []
    for entry in config:
        kind = entry.get("kind")
        params = {k: v for k, v in entry.items() if k != "kind"}
        if kind == "log_only":
            out.append(LogOnlyDestination(**params))
        elif kind == "slack":
            out.append(SlackDestination(**params))
        elif kind == "pagerduty":
            out.append(PagerDutyDestination(**params))
        elif kind == "opsgenie":
            out.append(OpsgenieDestination(**params))
        elif kind == "webhook":
            out.append(WebhookDestination(**params))
        else:
            raise ValueError(f"unknown alert destination kind: {kind!r}")
    return out
