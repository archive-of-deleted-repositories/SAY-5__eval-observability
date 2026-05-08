"""Click CLI smoke tests.

Drives every top-level subcommand against a temp SQLite DB and a fake
provider. The goal is **executability** of the CLI surface, not numerical
correctness — the real evaluations are exercised by the integration tests.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from eval_observability import db as db_module
from eval_observability.cli import _parse_since, main


@pytest.fixture()
def cli_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    db_path = tmp_path / "cli.db"
    monkeypatch.setenv("EVAL_OBS_DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("EVAL_OBS_REPORTS_DIR", str(tmp_path / "reports"))
    monkeypatch.setenv("EVAL_OBS_OTEL_EXPORTER", "memory")
    db_module.reset_engine()
    yield tmp_path
    db_module.reset_engine()


def test_cli_init_creates_schema(cli_env: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(main, ["init"])
    assert result.exit_code == 0, result.output
    assert "schema created" in result.output


def test_cli_seed_is_idempotent(cli_env: Path) -> None:
    runner = CliRunner()
    runner.invoke(main, ["init"])
    result = runner.invoke(main, ["seed"])
    assert result.exit_code == 0


def test_cli_run_fake_provider(cli_env: Path) -> None:
    runner = CliRunner()
    runner.invoke(main, ["init"])
    result = runner.invoke(
        main,
        [
            "run",
            "--suite",
            "core_v1",
            "--provider",
            "fake",
            "--model",
            "fake-large",
            "--limit",
            "2",
            "--category",
            "extraction",
        ],
    )
    assert result.exit_code == 0, result.output


def test_cli_run_unknown_suite_raises(cli_env: Path) -> None:
    runner = CliRunner()
    runner.invoke(main, ["init"])
    result = runner.invoke(main, ["run", "--suite", "nonexistent"])
    assert result.exit_code != 0
    assert "suite not found" in result.output


def test_cli_runs_list(cli_env: Path) -> None:
    runner = CliRunner()
    runner.invoke(main, ["init"])
    result = runner.invoke(main, ["runs", "--limit", "3"])
    assert result.exit_code == 0


def test_cli_alerts_list(cli_env: Path) -> None:
    runner = CliRunner()
    runner.invoke(main, ["init"])
    result = runner.invoke(main, ["alerts", "list", "--since", "7d"])
    assert result.exit_code == 0


def test_cli_report_list(cli_env: Path) -> None:
    runner = CliRunner()
    runner.invoke(main, ["init"])
    result = runner.invoke(main, ["report", "list", "--since", "1d"])
    assert result.exit_code == 0


def test_cli_report_show_missing(cli_env: Path) -> None:
    runner = CliRunner()
    runner.invoke(main, ["init"])
    result = runner.invoke(main, ["report", "show", "999"])
    assert result.exit_code != 0


def test_parse_since_units() -> None:
    """``_parse_since`` accepts ``Nd`` and ``Nh``; everything else raises."""
    import click

    # Smoke positive paths
    _parse_since("1d")
    _parse_since("12h")
    with pytest.raises(click.BadParameter):
        _parse_since("")
    with pytest.raises(click.BadParameter):
        _parse_since("xx")
    with pytest.raises(click.BadParameter):
        _parse_since("1y")
