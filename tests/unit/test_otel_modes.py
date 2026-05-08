"""Coverage for ``configure_tracing`` exporter selection.

The ``OTEL_MODE`` plumbing accepts three canonical values plus the legacy
``stdout`` alias for ``console``; an unknown value raises immediately.
"""

from __future__ import annotations

import pytest

from eval_observability.obs.otel import (
    VALID_MODES,
    InMemoryExporterHandle,
    _normalize_mode,
    configure_tracing,
    reset_tracing,
)


def test_valid_modes_set() -> None:
    assert {"memory", "console", "otlp"} == VALID_MODES


def test_normalize_console_alias() -> None:
    assert _normalize_mode("stdout") == "console"
    assert _normalize_mode("CONSOLE") == "console"


@pytest.mark.parametrize("mode", ["memory", "console", "otlp"])
def test_normalize_canonical(mode: str) -> None:
    assert _normalize_mode(mode) == mode


def test_normalize_unknown_raises() -> None:
    with pytest.raises(ValueError, match="unknown OTel exporter mode"):
        _normalize_mode("not-a-mode")


def test_memory_returns_handle() -> None:
    handle = configure_tracing(exporter="memory")
    assert isinstance(handle, InMemoryExporterHandle)
    handle.clear()
    reset_tracing()


def test_console_returns_none() -> None:
    handle = configure_tracing(exporter="console")
    assert handle is None
    reset_tracing()


def test_stdout_alias_routes_to_console() -> None:
    handle = configure_tracing(exporter="stdout")
    assert handle is None
    reset_tracing()


def test_otlp_does_not_raise_without_collector() -> None:
    """Configuring the OTLP exporter is allowed even when nothing is
    listening on 4317 — the gRPC client is lazy. Tearing down the processor
    should not raise either.
    """
    handle = configure_tracing(exporter="otlp", otlp_endpoint="http://localhost:4317")
    assert handle is None
    reset_tracing()
