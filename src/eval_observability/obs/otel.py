"""OpenTelemetry SDK setup with memory / console / OTLP exporter selection.

The exporter mode is selected by ``configure_tracing(exporter=...)`` or — at
process boot — by the ``EVAL_OBS_OTEL_EXPORTER`` env var (parsed by
``Settings``). The accepted values are::

    memory   InMemorySpanExporter — keep finished spans on a Python list.
             Used by every test except integration. (default)
    console  ConsoleSpanExporter — print each span to stdout. Useful for
             local debugging. ("stdout" is accepted as an alias.)
    otlp     OTLPSpanExporter (gRPC) — push to a real collector. The
             production wire-in mode; see ARCHITECTURE.md for the
             production wiring (Tempo/Jaeger via the otel-collector).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from opentelemetry import trace
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import SpanProcessor, TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    ConsoleSpanExporter,
    SimpleSpanProcessor,
)
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import Tracer

_provider: TracerProvider | None = None
_processors: list[SpanProcessor] = []

#: Canonical exporter modes. Aliases are normalized in ``_normalize_mode``.
VALID_MODES = {"memory", "console", "otlp"}


@dataclass
class InMemoryExporterHandle:
    """Wrapper exposing the InMemorySpanExporter for tests."""

    exporter: InMemorySpanExporter

    def finished_spans(self) -> list[Any]:
        return list(self.exporter.get_finished_spans())

    def clear(self) -> None:
        self.exporter.clear()


def reset_tracing() -> None:
    """Drop currently-attached span processors. Called between tests."""
    global _processors
    if _provider is not None:
        for proc in _processors:
            try:
                proc.shutdown()
            except Exception:
                pass
    _processors = []


def _normalize_mode(value: str) -> str:
    """Canonicalize ``OTEL_MODE`` values. ``stdout`` is accepted as an alias
    for ``console`` for backwards compatibility with the v1 docs.
    """
    lowered = value.lower()
    if lowered == "stdout":
        return "console"
    if lowered not in VALID_MODES:
        raise ValueError(
            f"unknown OTel exporter mode: {value!r} (expected one of {sorted(VALID_MODES)})"
        )
    return lowered


def configure_tracing(
    *,
    exporter: str = "memory",
    service_name: str = "eval-observability",
    otlp_endpoint: str | None = None,
) -> InMemoryExporterHandle | None:
    """Install (or reuse) a TracerProvider and attach the requested exporter.

    OTel's global ``set_tracer_provider`` is set-once, so we hold our own
    provider and reuse it across reconfigurations — adding the new processor
    and dropping previous ones. This keeps tests deterministic without
    fighting the SDK's set-once guard.

    The endpoint defaults to ``EVAL_OBS_OTEL_ENDPOINT`` (or
    ``http://localhost:4317`` when unset).
    """
    global _provider, _processors

    mode = _normalize_mode(exporter)
    endpoint = otlp_endpoint or os.environ.get("EVAL_OBS_OTEL_ENDPOINT", "http://localhost:4317")

    reset_tracing()

    if _provider is None:
        resource = Resource.create({SERVICE_NAME: service_name})
        _provider = TracerProvider(resource=resource)
        trace.set_tracer_provider(_provider)

    handle: InMemoryExporterHandle | None = None
    proc: SpanProcessor
    if mode == "memory":
        in_mem = InMemorySpanExporter()
        proc = SimpleSpanProcessor(in_mem)
        handle = InMemoryExporterHandle(exporter=in_mem)
    elif mode == "console":
        proc = SimpleSpanProcessor(ConsoleSpanExporter())
    else:  # mode == "otlp"
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

        proc = BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint))

    _provider.add_span_processor(proc)
    _processors.append(proc)
    return handle


def get_tracer(name: str = "eval_observability") -> Tracer:
    if _provider is None:
        return trace.get_tracer(name)
    return _provider.get_tracer(name)
