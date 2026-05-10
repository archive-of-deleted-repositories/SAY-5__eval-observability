"""Pluggable alert routing for regression detections.

The :class:`AlertDestination` Protocol defines the shape every destination
must satisfy: a single :meth:`send` method that takes a :class:`Alert` and
either returns or raises. The cron's :func:`dispatch_alerts` fans an alert
out across every configured destination, isolating each destination's
failure from the others.

Built-in destinations:

  * :class:`~.log_only.LogOnlyDestination` — prints to stdout (the default).
  * :class:`~.slack.SlackDestination` — POST to a Slack incoming-webhook URL.
  * :class:`~.pagerduty.PagerDutyDestination` — PagerDuty Events API v2.
  * :class:`~.opsgenie.OpsgenieDestination` — Opsgenie Alert API.
  * :class:`~.webhook.WebhookDestination` — generic HTTP POST with JSON body.

See ``README.md`` for the routing pattern and the ``alerts:`` config block.
"""

from .base import Alert, AlertDestination, DispatchResult, dispatch_alerts
from .factory import build_destinations
from .log_only import LogOnlyDestination
from .opsgenie import OpsgenieDestination
from .pagerduty import PagerDutyDestination
from .slack import SlackDestination
from .webhook import WebhookDestination

__all__ = [
    "Alert",
    "AlertDestination",
    "DispatchResult",
    "LogOnlyDestination",
    "OpsgenieDestination",
    "PagerDutyDestination",
    "SlackDestination",
    "WebhookDestination",
    "build_destinations",
    "dispatch_alerts",
]
