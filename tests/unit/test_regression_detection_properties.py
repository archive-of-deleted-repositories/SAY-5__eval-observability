"""Hypothesis property tests for the documented regression rule.

The cron job's ``generate_daily_report`` flags a category as a regression when
both conditions hold simultaneously (per ``ARCHITECTURE.md``)::

    delta < -regression_delta_threshold  AND  p_value < regression_p_threshold

The defaults are ``2pp`` (``0.02``) and ``0.05``. This module asserts that for
*any* synthesized run history, the persisted flagging matches the rule exactly.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given
from hypothesis import settings as hyp_settings
from hypothesis import strategies as st
from sqlalchemy.orm import Session

from eval_observability import db as db_module
from eval_observability.models import RegressionAlert, Run, RunItem, Suite
from eval_observability.regression.cron import generate_daily_report
from eval_observability.regression.stats import welch_t_test
from eval_observability.settings import Settings

DELTA_THRESHOLD = 0.02
P_THRESHOLD = 0.05


def _seed(
    s: Session,
    suite_id: int,
    model: str,
    *,
    current: dict[str, list[float]],
    prior: dict[str, list[float]],
    now: datetime,
) -> None:
    """Drop a small batch of items into the current / prior 7-day windows."""
    cur_started = now - timedelta(days=2)
    prior_started = now - timedelta(days=10)
    for category, scores in current.items():
        run = Run(
            suite_id=suite_id,
            model_version=model,
            started_at=cur_started,
            finished_at=cur_started + timedelta(seconds=10),
            status="completed",
            otel_trace_id="0" * 32,
        )
        s.add(run)
        s.flush()
        for i, score in enumerate(scores):
            s.add(
                RunItem(
                    run_id=run.id,
                    category=category,
                    example_id=f"cur-{category}-{i}",
                    score=score,
                    passed=score >= 0.5,
                    latency_ms=1.0,
                    cost_usd=0.0,
                    status="ok",
                )
            )
    for category, scores in prior.items():
        run = Run(
            suite_id=suite_id,
            model_version=model,
            started_at=prior_started,
            finished_at=prior_started + timedelta(seconds=10),
            status="completed",
            otel_trace_id="0" * 32,
        )
        s.add(run)
        s.flush()
        for i, score in enumerate(scores):
            s.add(
                RunItem(
                    run_id=run.id,
                    category=category,
                    example_id=f"prior-{category}-{i}",
                    score=score,
                    passed=score >= 0.5,
                    latency_ms=1.0,
                    cost_usd=0.0,
                    status="ok",
                )
            )


def _expected_flagged(current: dict[str, list[float]], prior: dict[str, list[float]]) -> set[str]:
    flagged: set[str] = set()
    for category in set(current) | set(prior):
        cur = current.get(category, [])
        pri = prior.get(category, [])
        cur_mean = sum(cur) / len(cur) if cur else 0.0
        pri_mean = sum(pri) / len(pri) if pri else 0.0
        delta = cur_mean - pri_mean
        p_value = welch_t_test(cur, pri).p_value if len(cur) >= 2 and len(pri) >= 2 else 1.0
        if delta < -DELTA_THRESHOLD and p_value < P_THRESHOLD:
            flagged.add(category)
    return flagged


# Strategies. Bounded scores in [0, 1] (pass-rate domain). Non-degenerate samples.
_score = st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False)
_score_list = st.lists(_score, min_size=2, max_size=12)
_category = st.sampled_from(["extraction", "summarization", "code", "reasoning"])
_window = st.dictionaries(_category, _score_list, min_size=1, max_size=4)


@hyp_settings(
    max_examples=40,
    deadline=None,
    suppress_health_check=[
        HealthCheck.function_scoped_fixture,
        HealthCheck.too_slow,
    ],
)
@given(current=_window, prior=_window)
def test_flagging_matches_documented_rule(
    tmp_path_factory: pytest.TempPathFactory,
    monkeypatch: pytest.MonkeyPatch,
    current: dict[str, list[float]],
    prior: dict[str, list[float]],
) -> None:
    tmp_path = tmp_path_factory.mktemp("flagging")
    db_path = tmp_path / "t.db"
    monkeypatch.setenv("EVAL_OBS_DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("EVAL_OBS_REPORTS_DIR", str(tmp_path / "reports"))
    db_module.reset_engine()
    db_module.create_all()

    now = datetime.now(UTC)
    expected = _expected_flagged(current, prior)

    with db_module.session_scope() as s:
        suite = Suite(name="core_v1", version="core_v1", manifest_hash="x")
        s.add(suite)
        s.flush()
        _seed(s, suite.id, "fake-large", current=current, prior=prior, now=now)

    settings = Settings(
        reports_dir=tmp_path / "reports",
        regression_delta_threshold=DELTA_THRESHOLD,
        regression_p_threshold=P_THRESHOLD,
    )
    with db_module.session_scope() as s:
        report = generate_daily_report(
            s,
            suite_name="core_v1",
            suite_version="core_v1",
            model_version="fake-large",
            now=now,
            settings=settings,
        )
        actual = {row["category"] for row in report.summary["rows"] if row["regression"] == "yes"}
        alerts = {
            a.category
            for a in s.query(RegressionAlert)
            .filter(RegressionAlert.model_version == "fake-large")
            .all()
        }
    assert actual == expected
    assert alerts == expected
    Path(report.file_path).unlink(missing_ok=True)
    db_module.reset_engine()


def test_documented_rule_constants_match_settings_defaults() -> None:
    """The constants we test against must be the framework defaults."""
    s = Settings()
    assert s.regression_delta_threshold == DELTA_THRESHOLD
    assert s.regression_p_threshold == P_THRESHOLD
