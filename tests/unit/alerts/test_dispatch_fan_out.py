"""Fan-out: a regression must hit every configured destination exactly once,
and a failing destination must not block the others.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from eval_observability import db as db_module
from eval_observability.alerts import (
    Alert,
    AlertDestination,
    LogOnlyDestination,
    OpsgenieDestination,
    PagerDutyDestination,
    SlackDestination,
    WebhookDestination,
    build_destinations,
    dispatch_alerts,
)
from eval_observability.models import Run, RunItem, Suite
from eval_observability.regression.cron import generate_daily_report
from eval_observability.settings import Settings


class _Recorder:
    """Bare-minimum class that satisfies :class:`AlertDestination`."""

    def __init__(self, name: str, fail: bool = False) -> None:
        self.name = name
        self.fail = fail
        self.received: list[Alert] = []

    def send(self, alert: Alert) -> None:
        self.received.append(alert)
        if self.fail:
            raise RuntimeError(f"{self.name}: synthetic failure")


def _alert(category: str = "extraction") -> Alert:
    return Alert(
        suite_name="core_v1",
        suite_version="core_v1",
        model_version="fake-large",
        category=category,
        delta=-0.04,
        p_value=0.001,
        current_mean=0.81,
        prior_mean=0.85,
        detected_at="2026-05-08T00:00:00+00:00",
    )


def test_each_destination_receives_alert_exactly_once() -> None:
    a, b, c, d = (_Recorder(n) for n in ("a", "b", "c", "d"))
    results = dispatch_alerts([_alert()], [a, b, c, d])
    assert [r.destination for r in results] == ["a", "b", "c", "d"]
    assert all(r.ok for r in results)
    for dest in (a, b, c, d):
        assert len(dest.received) == 1
        assert dest.received[0].category == "extraction"


def test_failing_destination_does_not_block_others() -> None:
    a = _Recorder("a")
    b = _Recorder("b", fail=True)
    c = _Recorder("c")
    d = _Recorder("d", fail=True)
    results = dispatch_alerts([_alert()], [a, b, c, d])
    by_name = {r.destination: r for r in results}
    assert by_name["a"].ok
    assert by_name["c"].ok
    assert not by_name["b"].ok
    assert "synthetic failure" in (by_name["b"].error or "")
    assert not by_name["d"].ok
    # Both healthy destinations still received the alert despite the failures.
    assert len(a.received) == 1
    assert len(c.received) == 1


def test_factory_builds_four_protocol_compliant_destinations() -> None:
    config = [
        {"kind": "slack", "webhook_url": "https://hooks.slack.com/x"},
        {"kind": "pagerduty", "integration_key": "k"},
        {"kind": "opsgenie", "api_key": "k"},
        {"kind": "webhook", "url": "https://example.com/h"},
    ]
    dests = build_destinations(config)
    assert isinstance(dests[0], SlackDestination)
    assert isinstance(dests[1], PagerDutyDestination)
    assert isinstance(dests[2], OpsgenieDestination)
    assert isinstance(dests[3], WebhookDestination)
    for dest in dests:
        assert isinstance(dest, AlertDestination)


def test_factory_default_log_only() -> None:
    [dest] = build_destinations(None)
    assert isinstance(dest, LogOnlyDestination)
    [dest] = build_destinations([])
    assert isinstance(dest, LogOnlyDestination)


def test_factory_unknown_kind_raises() -> None:
    with pytest.raises(ValueError, match="unknown alert destination"):
        build_destinations([{"kind": "carrier-pigeon"}])


# --------------------------------------------------------------------------- #
# End-to-end through the cron                                                  #
# --------------------------------------------------------------------------- #


@pytest.fixture()
def cron_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "t.db"
    monkeypatch.setenv("EVAL_OBS_DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("EVAL_OBS_REPORTS_DIR", str(tmp_path / "reports"))
    db_module.reset_engine()
    db_module.create_all()
    with db_module.session_scope() as s:
        s.add(Suite(name="core_v1", version="core_v1", manifest_hash="x"))
    yield tmp_path
    db_module.reset_engine()


def _seed_drop(session: Any, suite_id: int, model: str, now: datetime) -> None:
    """Seed a clear regression in 'extraction' (current 0.5 vs prior 0.95)."""
    cur_started = now - timedelta(days=2)
    prior_started = now - timedelta(days=10)
    cur_run = Run(
        suite_id=suite_id,
        model_version=model,
        started_at=cur_started,
        finished_at=cur_started + timedelta(seconds=10),
        status="completed",
        otel_trace_id="0" * 32,
    )
    prior_run = Run(
        suite_id=suite_id,
        model_version=model,
        started_at=prior_started,
        finished_at=prior_started + timedelta(seconds=10),
        status="completed",
        otel_trace_id="0" * 32,
    )
    session.add(cur_run)
    session.add(prior_run)
    session.flush()
    cur_scores = [0.50, 0.51, 0.49, 0.52, 0.48]
    prior_scores = [0.95, 0.94, 0.96, 0.95, 0.94]
    for i, sc in enumerate(cur_scores):
        session.add(
            RunItem(
                run_id=cur_run.id,
                category="extraction",
                example_id=f"cur-{i}",
                score=sc,
                passed=False,
                latency_ms=1.0,
                cost_usd=0.0,
                status="ok",
            )
        )
    for i, sc in enumerate(prior_scores):
        session.add(
            RunItem(
                run_id=prior_run.id,
                category="extraction",
                example_id=f"prior-{i}",
                score=sc,
                passed=True,
                latency_ms=1.0,
                cost_usd=0.0,
                status="ok",
            )
        )


def test_cron_fans_alert_out_to_all_four_destinations(cron_db: Path) -> None:
    settings = Settings(reports_dir=cron_db / "reports")
    now = datetime.now(UTC)
    with db_module.session_scope() as s:
        suite = s.query(Suite).first()
        _seed_drop(s, suite.id, "fake-large", now)

    a, b, c, d = (_Recorder(n) for n in ("a", "b", "c", "d"))
    with db_module.session_scope() as s:
        report = generate_daily_report(
            s,
            suite_name="core_v1",
            suite_version="core_v1",
            model_version="fake-large",
            now=now,
            settings=settings,
            alert_destinations=[a, b, c, d],
        )

    flagged = [row for row in report.summary["rows"] if row["regression"] == "yes"]
    assert flagged, report.summary
    assert flagged[0]["category"] == "extraction"

    # Each of the four destinations got exactly one alert.
    for dest in (a, b, c, d):
        assert len(dest.received) == 1, dest.name
        assert dest.received[0].category == "extraction"

    # Report.summary records the dispatch outcome for traceability.
    assert {entry["destination"] for entry in report.summary["alert_dispatch"]} == {
        "a",
        "b",
        "c",
        "d",
    }
    assert all(entry["ok"] for entry in report.summary["alert_dispatch"])


def test_cron_failed_destination_is_isolated(cron_db: Path) -> None:
    settings = Settings(reports_dir=cron_db / "reports")
    now = datetime.now(UTC)
    with db_module.session_scope() as s:
        suite = s.query(Suite).first()
        _seed_drop(s, suite.id, "fake-large", now)

    healthy = _Recorder("healthy")
    broken = _Recorder("broken", fail=True)
    with db_module.session_scope() as s:
        report = generate_daily_report(
            s,
            suite_name="core_v1",
            suite_version="core_v1",
            model_version="fake-large",
            now=now,
            settings=settings,
            alert_destinations=[broken, healthy],
        )

    # Healthy destination received the alert despite ``broken`` raising first.
    assert len(healthy.received) == 1
    by_name = {entry["destination"]: entry for entry in report.summary["alert_dispatch"]}
    assert by_name["healthy"]["ok"] is True
    assert by_name["broken"]["ok"] is False
    assert "synthetic failure" in (by_name["broken"]["error"] or "")
