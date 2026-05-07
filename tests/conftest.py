"""Shared pytest fixtures: in-memory DB and OTel exporter."""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest

os.environ.setdefault("EVAL_OBS_DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("EVAL_OBS_OTEL_EXPORTER", "memory")

from eval_observability import db as db_module  # noqa: E402
from eval_observability.obs.otel import (  # noqa: E402
    InMemoryExporterHandle,
    configure_tracing,
    reset_tracing,
)


@pytest.fixture()
def trace_handle() -> Iterator[InMemoryExporterHandle]:
    handle = configure_tracing(exporter="memory", service_name="eval-observability-test")
    assert handle is not None
    yield handle
    reset_tracing()


@pytest.fixture()
def fresh_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("EVAL_OBS_DATABASE_URL", f"sqlite:///{db_path}")
    db_module.reset_engine()
    db_module.create_all()
    yield
    db_module.reset_engine()
