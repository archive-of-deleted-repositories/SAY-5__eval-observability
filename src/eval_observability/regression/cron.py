"""Daily-report generator: walks recent runs, runs Welch's t-test, writes Markdown."""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..alerts import (
    Alert,
    AlertDestination,
    DispatchResult,
    LogOnlyDestination,
    dispatch_alerts,
)
from ..models import DailyReport, RegressionAlert, Run, RunItem, Suite
from ..settings import Settings, get_settings
from .stats import welch_t_test


def _windowed_scores(
    session: Session,
    suite_id: int,
    model_version: str,
    start: datetime,
    end: datetime,
) -> dict[str, list[float]]:
    rows = session.execute(
        select(RunItem.category, RunItem.score)
        .join(Run, RunItem.run_id == Run.id)
        .where(
            Run.suite_id == suite_id,
            Run.model_version == model_version,
            Run.started_at >= start,
            Run.started_at < end,
        )
    ).all()
    bucket: dict[str, list[float]] = defaultdict(list)
    for category, score in rows:
        bucket[category].append(float(score))
    return bucket


def _format_table(rows: list[dict[str, Any]]) -> str:
    headers = ["category", "current_mean", "prior_mean", "delta", "p_value", "regression"]
    out = ["| " + " | ".join(headers) + " |", "|" + "|".join(["---"] * len(headers)) + "|"]
    for row in rows:
        out.append(
            "| {category} | {current_mean:.4f} | {prior_mean:.4f} | "
            "{delta:+.4f} | {p_value:.4f} | {regression} |".format(**row)
        )
    return "\n".join(out)


def generate_daily_report(
    session: Session,
    *,
    suite_name: str,
    suite_version: str,
    model_version: str,
    now: datetime | None = None,
    settings: Settings | None = None,
    alert_destinations: list[AlertDestination] | None = None,
) -> DailyReport:
    """Generate (or return the existing) DailyReport for ``date(now)``.

    Idempotent on ``(suite, model_version, date)``. Newly inserted
    :class:`RegressionAlert` rows are fanned out to every configured alert
    destination via :func:`alerts.dispatch_alerts`. When the report for
    ``(suite, model, date)`` already exists, alerts are *not* re-fired.
    """
    settings = settings or get_settings()
    now = now or datetime.now(UTC)
    date_key = now.date().isoformat()

    suite = session.execute(
        select(Suite).where(Suite.name == suite_name, Suite.version == suite_version)
    ).scalar_one_or_none()
    if suite is None:
        raise ValueError(f"unknown suite: {suite_name}/{suite_version}")

    existing = session.execute(
        select(DailyReport).where(
            DailyReport.suite_id == suite.id,
            DailyReport.model_version == model_version,
            DailyReport.date == date_key,
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    current_start = now - timedelta(days=7)
    prior_start = current_start - timedelta(days=7)
    current_window = _windowed_scores(session, suite.id, model_version, current_start, now)
    prior_window = _windowed_scores(session, suite.id, model_version, prior_start, current_start)

    rows: list[dict[str, Any]] = []
    flagged: list[RegressionAlert] = []
    for category in sorted(set(current_window) | set(prior_window)):
        cur = current_window.get(category, [])
        prior = prior_window.get(category, [])
        cur_mean = sum(cur) / len(cur) if cur else 0.0
        prior_mean = sum(prior) / len(prior) if prior else 0.0
        delta = cur_mean - prior_mean
        if len(cur) >= 2 and len(prior) >= 2:
            t = welch_t_test(cur, prior)
            p_value = t.p_value
        else:
            p_value = 1.0
        is_regression = (
            delta < -settings.regression_delta_threshold
            and p_value < settings.regression_p_threshold
        )
        rows.append(
            {
                "category": category,
                "current_mean": cur_mean,
                "prior_mean": prior_mean,
                "delta": delta,
                "p_value": p_value,
                "regression": "yes" if is_regression else "no",
            }
        )
        if is_regression:
            alert = RegressionAlert(
                suite_id=suite.id,
                model_version=model_version,
                category=category,
                current_mean=cur_mean,
                prior_mean=prior_mean,
                delta=delta,
                p_value=p_value,
            )
            session.add(alert)
            flagged.append(alert)

    settings.reports_dir.mkdir(parents=True, exist_ok=True)
    file_name = f"{date_key}-{suite.name}-{model_version}.md"
    file_path = settings.reports_dir / file_name

    md_parts = [
        f"# {suite.name}/{suite.version} — {model_version} — {date_key}",
        "",
        "## Summary",
        "",
        _format_table(rows) if rows else "_No runs in the last 14 days._",
        "",
        "## Regressions flagged",
        "",
    ]
    if flagged:
        for alert in flagged:
            md_parts.append(
                f"- **{alert.category}**: "
                f"{alert.delta * 100:+.2f}pp (p={alert.p_value:.4f}) "
                f"current={alert.current_mean:.4f} prior={alert.prior_mean:.4f}"
            )
    else:
        md_parts.append("_None — no statistically significant regressions detected._")

    md_parts.extend(
        [
            "",
            "## Notes",
            "",
            f"- Window: 7-day current vs prior 7-day window ending {now.isoformat()}.",
            f"- Threshold: delta < -{settings.regression_delta_threshold:.3f} "
            f"AND p < {settings.regression_p_threshold:.3f}.",
            "- Trace links: see Postgres `runs.otel_trace_id` for individual traces.",
            "",
        ]
    )
    file_path.write_text("\n".join(md_parts))

    dispatch_results: list[DispatchResult] = []
    if flagged:
        destinations = alert_destinations or [LogOnlyDestination()]
        outbound = [
            Alert(
                suite_name=suite_name,
                suite_version=suite_version,
                model_version=model_version,
                category=a.category,
                delta=a.delta,
                p_value=a.p_value,
                current_mean=a.current_mean,
                prior_mean=a.prior_mean,
                detected_at=now.isoformat(),
            )
            for a in flagged
        ]
        dispatch_results = dispatch_alerts(outbound, destinations)

    summary = {
        "rows": rows,
        "flagged_count": len(flagged),
        "current_window_start": current_start.isoformat(),
        "prior_window_start": prior_start.isoformat(),
        "alert_dispatch": [
            {"destination": r.destination, "ok": r.ok, "error": r.error} for r in dispatch_results
        ],
    }
    report = DailyReport(
        suite_id=suite.id,
        model_version=model_version,
        date=date_key,
        file_path=str(file_path),
        summary=summary,
    )
    session.add(report)
    session.flush()
    return report
