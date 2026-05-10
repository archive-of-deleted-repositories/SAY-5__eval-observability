"""Click CLI: run evals, generate daily reports, list reports and alerts."""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table
from sqlalchemy import desc, select

from . import __version__
from .alerts import build_destinations
from .db import create_all, session_scope
from .models import DailyReport, RegressionAlert, Run, Suite
from .obs.logs import configure_logging, get_logger
from .obs.otel import configure_tracing
from .providers.registry import get_provider
from .regression.cron import generate_daily_report
from .runner import run_suite
from .settings import get_settings

console = Console()
logger = get_logger(__name__)


def _parse_since(since: str) -> datetime:
    if not since:
        raise click.BadParameter("missing --since")
    unit = since[-1]
    try:
        value = int(since[:-1])
    except ValueError as exc:
        raise click.BadParameter(f"bad --since: {since!r}") from exc
    delta = {"d": timedelta(days=value), "h": timedelta(hours=value)}.get(unit)
    if delta is None:
        raise click.BadParameter(f"bad --since unit: {unit!r}")
    return datetime.now(UTC) - delta


@click.group()
@click.version_option(__version__, prog_name="eval-obs")
def main() -> None:
    """eval-observability — LLM eval framework with OTel tracing and regression detection."""
    settings = get_settings()
    configure_tracing(
        exporter=settings.otel_exporter,
        service_name=settings.service_name,
        otlp_endpoint=settings.otel_endpoint,
    )
    configure_logging(json_output=True)


@main.command("init")
def init_db() -> None:
    """Create all tables (idempotent)."""
    create_all()
    click.echo("schema created")


@main.command("seed")
def seed() -> None:
    """Stub seed — kept for parity with the Makefile target."""
    create_all()
    click.echo("nothing to seed; schema ensured")


@main.command()
@click.option("--suite", default="core_v1")
@click.option("--provider", default="fake")
@click.option("--model", default="fake-large")
@click.option("--category", "categories", multiple=True, help="Restrict to category(s).")
@click.option("--limit", type=int, default=None, help="Limit examples per category.")
@click.option("--smoke", is_flag=True, help="Compare summary against committed baseline.")
@click.option("--baseline", type=click.Path(path_type=Path), default=None)
def run(
    suite: str,
    provider: str,
    model: str,
    categories: tuple[str, ...],
    limit: int | None,
    smoke: bool,
    baseline: Path | None,
) -> None:
    """Run a suite end-to-end."""
    settings = get_settings()
    create_all()

    suite_root = settings.suites_root / suite
    if not suite_root.exists():
        raise click.ClickException(f"suite not found: {suite_root}")

    chat_provider = get_provider(provider)
    cats = list(categories) if categories else None

    with session_scope() as session:
        summary = run_suite(
            session,
            suite_root=suite_root,
            suite_name=suite,
            suite_version="core_v1",
            provider=chat_provider,
            model=model,
            categories=cats,
            limit=limit,
        )

    table = Table(title=f"run #{summary.run_id} — {suite} — {model}")
    table.add_column("category")
    table.add_column("n", justify="right")
    table.add_column("mean_score", justify="right")
    table.add_column("pass_rate", justify="right")
    for cat, stats in summary.per_category.items():
        table.add_row(
            cat,
            f"{int(stats['n'])}",
            f"{stats['mean_score']:.4f}",
            f"{stats['pass_rate']:.4f}",
        )
    console.print(table)
    console.print(f"trace_id: {summary.trace_id}")
    console.print(f"total: {summary.total_passed}/{summary.total_examples} passed")

    if smoke:
        baseline_path = baseline or settings.baselines_dir / f"{suite}_{provider}.json"
        if not baseline_path.exists():
            raise click.ClickException(f"baseline missing: {baseline_path}")
        expected = json.loads(baseline_path.read_text())
        actual = {
            "per_category": summary.per_category,
            "total_examples": summary.total_examples,
            "total_passed": summary.total_passed,
            "model": model,
        }
        if expected != actual:
            console.print("[red]baseline mismatch[/red]")
            console.print_json(data={"expected": expected, "actual": actual})
            sys.exit(2)
        console.print("[green]baseline match[/green]")


@main.group()
def cron() -> None:
    """Scheduled jobs (daily reports, etc.)."""


@cron.command("daily")
@click.option("--suite", default="core_v1")
@click.option("--model", default="fake-large")
@click.option("--now", default=None, help="Override 'now' for deterministic runs (ISO-8601).")
def cron_daily(suite: str, model: str, now: str | None) -> None:
    """Generate the daily regression report."""
    settings = get_settings()
    create_all()
    when = datetime.fromisoformat(now) if now else None
    destinations = build_destinations(settings.alerts)
    with session_scope() as session:
        report = generate_daily_report(
            session,
            suite_name=suite,
            suite_version="core_v1",
            model_version=model,
            now=when,
            settings=settings,
            alert_destinations=destinations,
        )
        click.echo(f"report id={report.id} path={report.file_path}")


@main.group()
def report() -> None:
    """Inspect daily reports."""


@report.command("list")
@click.option("--suite", default=None)
@click.option("--since", default="7d")
def report_list(suite: str | None, since: str) -> None:
    cutoff = _parse_since(since)
    with session_scope() as session:
        stmt = select(DailyReport).where(DailyReport.generated_at >= cutoff)
        if suite is not None:
            stmt = stmt.join(Suite).where(Suite.name == suite)
        rows = session.execute(stmt.order_by(desc(DailyReport.generated_at))).scalars().all()
        table = Table(title="daily reports")
        table.add_column("id", justify="right")
        table.add_column("date")
        table.add_column("suite_id", justify="right")
        table.add_column("model")
        table.add_column("file_path")
        for r in rows:
            table.add_row(str(r.id), r.date, str(r.suite_id), r.model_version, r.file_path)
        console.print(table)


@report.command("show")
@click.argument("report_id", type=int)
def report_show(report_id: int) -> None:
    with session_scope() as session:
        rep = session.get(DailyReport, report_id)
        if rep is None:
            raise click.ClickException(f"no report id={report_id}")
        click.echo(Path(rep.file_path).read_text())


@main.group()
def alerts() -> None:
    """Inspect regression alerts."""


@alerts.command("list")
@click.option("--since", default="7d")
def alerts_list(since: str) -> None:
    cutoff = _parse_since(since)
    with session_scope() as session:
        rows = (
            session.execute(
                select(RegressionAlert)
                .where(RegressionAlert.detected_at >= cutoff)
                .order_by(desc(RegressionAlert.detected_at))
            )
            .scalars()
            .all()
        )
        table = Table(title="regression alerts")
        table.add_column("id", justify="right")
        table.add_column("category")
        table.add_column("model")
        table.add_column("delta", justify="right")
        table.add_column("p_value", justify="right")
        table.add_column("detected_at")
        for a in rows:
            table.add_row(
                str(a.id),
                a.category,
                a.model_version,
                f"{a.delta:+.4f}",
                f"{a.p_value:.4f}",
                a.detected_at.isoformat(),
            )
        console.print(table)


@main.command("runs")
@click.option("--limit", type=int, default=10)
def runs_list(limit: int) -> None:
    """List recent runs."""
    with session_scope() as session:
        rows = session.execute(select(Run).order_by(desc(Run.id)).limit(limit)).scalars().all()
        table = Table(title=f"recent runs (n={len(rows)})")
        table.add_column("id", justify="right")
        table.add_column("model")
        table.add_column("status")
        table.add_column("started")
        table.add_column("trace_id")
        for r in rows:
            table.add_row(
                str(r.id),
                r.model_version,
                r.status,
                r.started_at.isoformat() if r.started_at else "-",
                r.otel_trace_id or "-",
            )
        console.print(table)


if __name__ == "__main__":
    main()
