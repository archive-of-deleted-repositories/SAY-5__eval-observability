"""OpenTelemetry SDK setup with stdout / in-memory / OTLP exporter selection."""

from __future__ import annotations

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


def configure_tracing(
    *,
    exporter: str = "memory",
    service_name: str = "eval-observability",
    otlp_endpoint: str = "http://localhost:4317",
) -> InMemoryExporterHandle | None:
    """Install (or reuse) a TracerProvider and attach the requested exporter.

    OTel's global ``set_tracer_provider`` is set-once, so we hold our own
    provider and reuse it across reconfigurations — adding the new processor
    and dropping previous ones. This keeps tests deterministic without
    fighting the SDK's set-once guard.
    """
    global _provider, _processors

    reset_tracing()

    if _provider is None:
        resource = Resource.create({SERVICE_NAME: service_name})
        _provider = TracerProvider(resource=resource)
        trace.set_tracer_provider(_provider)

    handle: InMemoryExporterHandle | None = None
    proc: SpanProcessor
    if exporter == "memory":
        in_mem = InMemorySpanExporter()
        proc = SimpleSpanProcessor(in_mem)
        handle = InMemoryExporterHandle(exporter=in_mem)
    elif exporter == "stdout":
        proc = SimpleSpanProcessor(ConsoleSpanExporter())
    elif exporter == "otlp":
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

        proc = BatchSpanProcessor(OTLPSpanExporter(endpoint=otlp_endpoint))
    else:
        raise ValueError(f"unknown OTel exporter: {exporter!r}")

    _provider.add_span_processor(proc)
    _processors.append(proc)
    return handle


def get_tracer(name: str = "eval_observability") -> Tracer:
    if _provider is None:
        return trace.get_tracer(name)
    return _provider.get_tracer(name)
