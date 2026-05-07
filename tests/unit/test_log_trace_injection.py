"""structlog must inject trace_id and span_id from the active OTel context."""

from __future__ import annotations

import io
import json
from typing import Any

import pytest
import structlog

from eval_observability.obs.logs import configure_logging
from eval_observability.obs.otel import configure_tracing, get_tracer, reset_tracing


@pytest.fixture()
def tracing() -> Any:
    handle = configure_tracing(exporter="memory")
    yield handle
    reset_tracing()


def test_trace_id_injected(tracing: Any) -> None:
    buf = io.StringIO()
    configure_logging(json_output=True)
    structlog.configure(
        processors=[
            *structlog.get_config()["processors"][:-1],
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(file=buf),
    )
    logger = structlog.get_logger("test")
    tracer = get_tracer("test")
    with tracer.start_as_current_span("outer"):
        logger.info("hello")
    line = buf.getvalue().strip().splitlines()[-1]
    parsed = json.loads(line)
    assert "trace_id" in parsed
    assert "span_id" in parsed
    assert len(parsed["trace_id"]) == 32
    assert len(parsed["span_id"]) == 16


def test_no_trace_id_outside_span(tracing: Any) -> None:
    buf = io.StringIO()
    configure_logging(json_output=True)
    structlog.configure(
        processors=[
            *structlog.get_config()["processors"][:-1],
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(file=buf),
    )
    logger = structlog.get_logger("test")
    logger.info("no_span")
    line = buf.getvalue().strip().splitlines()[-1]
    parsed = json.loads(line)
    assert "trace_id" not in parsed
