"""Core types for the alerts subsystem.

The :class:`Alert` dataclass is the wire format every destination receives.
:class:`AlertDestination` is a runtime Protocol so user code can define new
destinations without subclassing — anything with a compatible ``send``
method satisfies the protocol.

:func:`dispatch_alerts` is the fan-out entry point used by the cron when a
regression is detected. It calls every destination's ``send`` exactly once
and isolates failures so a misconfigured webhook can't block the rest.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Alert:
    """A single regression-flagged event delivered to every destination."""

    suite_name: str
    suite_version: str
    model_version: str
    category: str
    delta: float
    p_value: float
    current_mean: float
    prior_mean: float
    detected_at: str  # ISO-8601
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def title(self) -> str:
        return (
            f"[{self.suite_name}/{self.suite_version}] regression in "
            f"{self.category} ({self.model_version})"
        )

    @property
    def summary(self) -> str:
        return (
            f"{self.category}: {self.delta * 100:+.2f}pp "
            f"(p={self.p_value:.4f}) "
            f"current={self.current_mean:.4f} prior={self.prior_mean:.4f}"
        )


@runtime_checkable
class AlertDestination(Protocol):
    """Sink for an :class:`Alert`. Implementations must be side-effecting."""

    name: str

    def send(self, alert: Alert) -> None:
        """Deliver ``alert``. Raise on failure — the dispatcher will log and
        carry on with the next destination.
        """
        ...


@dataclass(frozen=True)
class DispatchResult:
    """Per-destination delivery outcome from :func:`dispatch_alerts`."""

    destination: str
    ok: bool
    error: str | None = None


def dispatch_alerts(
    alerts: list[Alert], destinations: list[AlertDestination]
) -> list[DispatchResult]:
    """Fan ``alerts`` out across every ``destination``.

    Each destination is called **exactly once per alert** (so two alerts +
    three destinations = six calls). A failing destination is logged at
    ``warning`` level and does not stop downstream destinations from
    receiving the same alert.
    """
    results: list[DispatchResult] = []
    for alert in alerts:
        for dest in destinations:
            try:
                dest.send(alert)
                results.append(DispatchResult(destination=dest.name, ok=True))
            except Exception as exc:  # noqa: BLE001 — destinations are user-provided
                logger.warning(
                    "alert_destination_failed",
                    extra={
                        "destination": dest.name,
                        "category": alert.category,
                        "error": f"{type(exc).__name__}: {exc}",
                    },
                )
                results.append(
                    DispatchResult(
                        destination=dest.name,
                        ok=False,
                        error=f"{type(exc).__name__}: {exc}",
                    )
                )
    return results
