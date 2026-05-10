"""LogOnlyDestination — the default, prints every alert to stdout."""

from __future__ import annotations

import sys
from dataclasses import dataclass

from .base import Alert


@dataclass
class LogOnlyDestination:
    """Print alerts to stdout. The default when no ``alerts:`` config is set."""

    name: str = "log_only"

    def send(self, alert: Alert) -> None:
        print(f"ALERT  {alert.title}\n  {alert.summary}", file=sys.stdout)
