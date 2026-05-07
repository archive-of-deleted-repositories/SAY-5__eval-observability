"""Integration test: full suite run + cron, gated on RUN_INTEGRATION=1."""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from eval_observability import db as db_module
from eval_observability.providers.fake import FakeProvider
from eval_observability.regression.cron import generate_daily_report
from eval_observability.runner import run_suite
from eval_observability.settings import Settings

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_INTEGRATION") != "1",
    reason="set RUN_INTEGRATION=1 to enable",
)


def test_full_suite_then_cron(fresh_db, trace_handle, tmp_path: Path) -> None:
    settings = Settings(reports_dir=tmp_path / "reports")
    suite_root = Path("eval/suites/core_v1")

    with db_module.session_scope() as session:
        summary = run_suite(
            session,
            suite_root=suite_root,
            suite_name="core_v1",
            suite_version="core_v1",
            provider=FakeProvider(),
            model="fake-large",
        )
    assert summary.total_examples == 60

    from eval_observability.models import Run, RunItem, Suite

    with db_module.session_scope() as s:
        suite = s.query(Suite).first()
        assert suite is not None
        prior_started = datetime.now(UTC) - timedelta(days=10)
        run = Run(
            suite_id=suite.id,
            model_version="fake-large",
            started_at=prior_started,
            finished_at=prior_started + timedelta(seconds=10),
            status="completed",
            otel_trace_id="0" * 32,
        )
        s.add(run)
        s.flush()
        for i in range(5):
            s.add(
                RunItem(
                    run_id=run.id,
                    category="extraction",
                    example_id=f"prior-{i}",
                    score=0.95,
                    passed=True,
                    latency_ms=1.0,
                    cost_usd=0.0,
                    status="ok",
                )
            )

    with db_module.session_scope() as session:
        report = generate_daily_report(
            session,
            suite_name="core_v1",
            suite_version="core_v1",
            model_version="fake-large",
            settings=settings,
        )
    assert Path(report.file_path).exists()
    assert report.summary is not None
    assert "rows" in report.summary
