"""Suite orchestrator: walks the (category, example) matrix; persists items and emits spans."""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode
from sqlalchemy import select
from sqlalchemy.orm import Session

from .categories import CATEGORIES, Example
from .models import Run, RunItem, Suite
from .obs.logs import get_logger
from .obs.otel import get_tracer
from .providers.base import ChatMessage, ChatProvider

logger = get_logger(__name__)


@dataclass
class RunSummary:
    run_id: int
    suite_name: str
    suite_version: str
    model_version: str
    started_at: datetime
    finished_at: datetime
    per_category: dict[str, dict[str, float]]
    total_examples: int
    total_passed: int
    trace_id: str


def _manifest_hash(examples: list[Example]) -> str:
    payload = json.dumps(
        [(e.category, e.id, repr(e.input), repr(e.gold)) for e in examples],
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def load_suite(suite_root: Path, *, categories: list[str] | None = None) -> list[Example]:
    cats = categories or list(CATEGORIES)
    out: list[Example] = []
    for cat_name in cats:
        module = CATEGORIES[cat_name]
        path = suite_root / f"{cat_name}.yaml"
        out.extend(module.load_suite(path))
    return out


def _ensure_suite(session: Session, *, name: str, version: str, manifest_hash: str) -> Suite:
    suite = session.execute(
        select(Suite).where(Suite.name == name, Suite.version == version)
    ).scalar_one_or_none()
    if suite is None:
        suite = Suite(name=name, version=version, manifest_hash=manifest_hash)
        session.add(suite)
        session.flush()
    elif suite.manifest_hash != manifest_hash:
        suite.manifest_hash = manifest_hash
        session.flush()
    return suite


def run_suite(
    session: Session,
    *,
    suite_root: Path,
    suite_name: str,
    suite_version: str,
    provider: ChatProvider,
    model: str,
    categories: list[str] | None = None,
    limit: int | None = None,
) -> RunSummary:
    """Run a suite end-to-end, persisting items and emitting OTel spans.

    Span hierarchy:
        suite_run
          └── category_run
                └── example_run
                      ├── llm_call
                      └── score
    """
    examples = load_suite(suite_root, categories=categories)
    if limit is not None:
        examples = examples[:limit]
    manifest = _manifest_hash(examples)
    suite = _ensure_suite(session, name=suite_name, version=suite_version, manifest_hash=manifest)
    started_at = datetime.now(UTC)

    tracer = get_tracer(__name__)
    with tracer.start_as_current_span(
        "suite_run",
        attributes={
            "suite_name": suite_name,
            "suite_version": suite_version,
            "model_version": model,
            "started_at": started_at.isoformat(),
            "n_examples": len(examples),
        },
    ) as suite_span:
        ctx = suite_span.get_span_context()
        trace_id_hex = f"{ctx.trace_id:032x}"
        run = Run(
            suite_id=suite.id,
            model_version=model,
            started_at=started_at,
            otel_trace_id=trace_id_hex,
            status="running",
        )
        session.add(run)
        session.flush()

        per_category: dict[str, list[RunItem]] = {}
        for cat_name in CATEGORIES if categories is None else categories:
            cat_examples = [ex for ex in examples if ex.category == cat_name]
            if not cat_examples:
                continue
            with tracer.start_as_current_span(
                "category_run",
                attributes={"category": cat_name, "n_examples": len(cat_examples)},
            ):
                module = CATEGORIES[cat_name]
                items: list[RunItem] = []
                for example in cat_examples:
                    item = _run_one(
                        tracer=tracer,
                        run_id=run.id,
                        example=example,
                        module=module,
                        provider=provider,
                        model=model,
                    )
                    session.add(item)
                    items.append(item)
                per_category[cat_name] = items
                session.flush()

        finished_at = datetime.now(UTC)
        summary_per_cat: dict[str, dict[str, float]] = {}
        total_passed = 0
        for cat_name, items in per_category.items():
            n = len(items)
            mean_score = sum(i.score for i in items) / n if n else 0.0
            passed = sum(1 for i in items if i.passed)
            total_passed += passed
            summary_per_cat[cat_name] = {
                "n": float(n),
                "mean_score": mean_score,
                "pass_rate": passed / n if n else 0.0,
            }
        run.finished_at = finished_at
        run.status = "completed"
        run.summary = {"per_category": summary_per_cat}
        suite_span.set_attribute("total_examples", len(examples))
        suite_span.set_attribute("total_passed", total_passed)

    return RunSummary(
        run_id=run.id,
        suite_name=suite_name,
        suite_version=suite_version,
        model_version=model,
        started_at=started_at,
        finished_at=finished_at,
        per_category=summary_per_cat,
        total_examples=len(examples),
        total_passed=total_passed,
        trace_id=trace_id_hex,
    )


def _run_one(
    *,
    tracer: trace.Tracer,
    run_id: int,
    example: Example,
    module: Any,
    provider: ChatProvider,
    model: str,
) -> RunItem:
    gold_hash = hashlib.sha256(repr(example.gold).encode("utf-8")).hexdigest()[:16]
    with tracer.start_as_current_span(
        "example_run",
        attributes={
            "category": example.category,
            "example_id": example.id,
            "gold_hash": gold_hash,
        },
    ) as ex_span:
        prompt = module.build_prompt(example)
        messages = [ChatMessage(role="user", content=prompt)]
        ex_ctx = ex_span.get_span_context()
        span_id_hex = f"{ex_ctx.span_id:016x}"

        output_text = ""
        latency_ms = 0.0
        cost_usd = 0.0
        status = "ok"
        error: str | None = None
        try:
            with tracer.start_as_current_span("llm_call") as llm_span:
                t0 = time.perf_counter()
                resp = provider.chat(messages, model=model)
                latency_ms = (time.perf_counter() - t0) * 1000.0
                cost_usd = resp.cost_usd
                output_text = resp.text
                llm_span.set_attribute("model", resp.model)
                llm_span.set_attribute("tokens_in", resp.tokens_in)
                llm_span.set_attribute("tokens_out", resp.tokens_out)
                llm_span.set_attribute("cost_usd", resp.cost_usd)
                llm_span.set_attribute("latency_ms", latency_ms)
                llm_span.set_attribute("retry_count", 0)
        except Exception as exc:  # noqa: BLE001
            status = "error"
            error = f"{type(exc).__name__}: {exc}"
            ex_span.set_status(Status(StatusCode.ERROR, error))
            logger.error("llm_call_failed", category=example.category, example_id=example.id)

        if status == "ok":
            with tracer.start_as_current_span("score") as score_span:
                try:
                    result = module.score(example, output_text)
                except Exception as exc:  # noqa: BLE001
                    status = "error"
                    error = f"score:{type(exc).__name__}: {exc}"
                    score_span.set_status(Status(StatusCode.ERROR, error))
                    score_value, passed, details = 0.0, False, {}
                else:
                    score_value = float(result.score)
                    passed = bool(result.passed)
                    details = result.details
                score_span.set_attribute("metric_name", example.category)
                score_span.set_attribute("score", score_value)
                score_span.set_attribute("passed", passed)
        else:
            score_value, passed, details = 0.0, False, {}

        ex_span.set_attribute("score", score_value)
        ex_span.set_attribute("passed", passed)

        return RunItem(
            run_id=run_id,
            category=example.category,
            example_id=example.id,
            output_text=output_text,
            score=score_value,
            passed=passed,
            latency_ms=latency_ms,
            cost_usd=cost_usd,
            span_id=span_id_hex,
            status=status,
            error=error,
            details=details,
        )
