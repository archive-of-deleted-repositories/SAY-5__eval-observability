"""Tiny stdlib-only HTTP POST helper used by every HTTP-based destination.

We avoid pulling in ``requests`` / ``httpx`` because the alerts subsystem
should not impose new runtime dependencies. Tests patch :func:`post_json`
directly to avoid the network.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

DEFAULT_TIMEOUT_S = 5.0


def post_json(
    url: str,
    payload: dict[str, Any],
    *,
    headers: dict[str, str] | None = None,
    timeout: float = DEFAULT_TIMEOUT_S,
) -> tuple[int, str]:
    """POST ``payload`` as JSON to ``url`` and return ``(status, body)``.

    Raises :class:`urllib.error.URLError` on connection failure and
    :class:`urllib.error.HTTPError` on non-2xx responses.
    """
    body = json.dumps(payload).encode("utf-8")
    merged_headers = {"Content-Type": "application/json"}
    if headers:
        merged_headers.update(headers)
    req = urllib.request.Request(  # noqa: S310 — caller-supplied URL is trusted
        url, data=body, headers=merged_headers, method="POST"
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
        return resp.status, resp.read().decode("utf-8", errors="replace")
