"""Daily reports must be idempotent on (suite, model_version, date)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from eval_observability import db as db_module
from eval_observability.models import Run, RunItem, Suite
from eval_observability.regression.cron import generate_daily_report
from eval_observability.settings import Settings


def _seed_runs(session, suite_id, model, scores_per_day):
    base = datetime.now(UTC)
    for days_ago, by_cat in scores_per_day.items():
        started = base - timedelta(days=days_ago, hours=1)
        run = Run(
            suite_id=suite_id,
            model_version=model,
            started_at=started,
            finished_at=started + timedelta(seconds=30),
            status="completed",
            otel_trace_id="0" * 32,
        )
        session.add(run)
        session.flush()
        for category, scores in by_cat.items():
            for i, s in enumerate(scores):
                session.add(
                    RunItem(
                        run_id=run.id,
                        category=category,
                        example_id=f"{category}-{days_ago}-{i}",
                        score=s,
                        passed=s >= 0.5,
                        latency_ms=1.0,
                        cost_usd=0.0,
                        status="ok",
                    )
                )


@pytest.fixture()
def session(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "t.db"
    monkeypatch.setenv("EVAL_OBS_DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("EVAL_OBS_REPORTS_DIR", str(tmp_path / "reports"))
    db_module.reset_engine()
    db_module.create_all()
    with db_module.session_scope() as s:
        suite = Suite(name="core_v1", version="core_v1", manifest_hash="x")
        s.add(suite)
        s.flush()
    yield
    db_module.reset_engine()


def test_daily_report_idempotent(session, tmp_path: Path) -> None:
    settings = Settings(reports_dir=tmp_path / "reports")
    with db_module.session_scope() as s:
        suite = s.query(Suite).first()
        assert suite is not None
        _seed_runs(
            s,
            suite.id,
            "fake-large",
            {
                1: {"extraction": [0.9, 0.85, 0.92, 0.88, 0.95]},
                2: {"extraction": [0.91, 0.88, 0.9, 0.87, 0.93]},
                10: {"extraction": [0.95, 0.92, 0.94, 0.96, 0.93]},
                11: {"extraction": [0.97, 0.95, 0.94, 0.96, 0.95]},
            },
        )
    with db_module.session_scope() as s:
        first = generate_daily_report(
            s,
            suite_name="core_v1",
            suite_version="core_v1",
            model_version="fake-large",
            settings=settings,
        )
        first_id = first.id
        first_path = first.file_path
    with db_module.session_scope() as s:
        second = generate_daily_report(
            s,
            suite_name="core_v1",
            suite_version="core_v1",
            model_version="fake-large",
            settings=settings,
        )
        assert second.id == first_id
        assert second.file_path == first_path


def test_daily_report_flags_regression(session, tmp_path: Path) -> None:
    settings = Settings(reports_dir=tmp_path / "reports")
    with db_module.session_scope() as s:
        suite = s.query(Suite).first()
        assert suite is not None
        _seed_runs(
            s,
            suite.id,
            "fake-large",
            {
                1: {"extraction": [0.70, 0.71, 0.72, 0.69, 0.70, 0.71, 0.70]},
                2: {"extraction": [0.71, 0.70, 0.69, 0.72, 0.71, 0.70, 0.71]},
                10: {"extraction": [0.92, 0.91, 0.93, 0.92, 0.91, 0.92, 0.93]},
                11: {"extraction": [0.93, 0.92, 0.91, 0.93, 0.92, 0.91, 0.92]},
            },
        )
    with db_module.session_scope() as s:
        report = generate_daily_report(
            s,
            suite_name="core_v1",
            suite_version="core_v1",
            model_version="fake-large",
            settings=settings,
        )
        assert report.summary is not None
        assert report.summary["flagged_count"] >= 1
