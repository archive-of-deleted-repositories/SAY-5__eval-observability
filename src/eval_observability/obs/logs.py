"""structlog configuration with OTel trace_id/span_id injection."""

from __future__ import annotations

import logging
from collections.abc import MutableMapping
from typing import Any

import structlog
from opentelemetry import trace


def _otel_context_processor(
    _logger: object, _method_name: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    span = trace.get_current_span()
    ctx = span.get_span_context()
    if ctx.is_valid:
        event_dict.setdefault("trace_id", f"{ctx.trace_id:032x}")
        event_dict.setdefault("span_id", f"{ctx.span_id:016x}")
    return event_dict


def configure_logging(level: int = logging.INFO, *, json_output: bool = True) -> None:
    """Configure structlog to emit JSON with OTel context fields injected."""
    timestamper = structlog.processors.TimeStamper(fmt="iso")
    processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        timestamper,
        _otel_context_processor,
    ]
    if json_output:
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer(colors=False))

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str = "eval_observability") -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)  # type: ignore[no-any-return]
