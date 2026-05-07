"""End-to-end span hierarchy assertions on a hermetic suite run."""

from __future__ import annotations

from pathlib import Path

from eval_observability import db as db_module
from eval_observability.providers.fake import FakeProvider
from eval_observability.runner import run_suite

SUITE_ROOT = Path("eval/suites/core_v1")


def test_full_suite_span_tree(fresh_db, trace_handle) -> None:
    with db_module.session_scope() as session:
        summary = run_suite(
            session,
            suite_root=SUITE_ROOT,
            suite_name="core_v1",
            suite_version="core_v1",
            provider=FakeProvider(),
            model="fake-large",
        )
    assert summary.total_examples == 60

    spans = trace_handle.finished_spans()
    by_name: dict[str, list] = {}
    for sp in spans:
        by_name.setdefault(sp.name, []).append(sp)

    # Expected counts: 1 suite, 6 categories, 60 example_run, 60 llm_call, 60 score.
    assert len(by_name["suite_run"]) == 1
    assert len(by_name["category_run"]) == 6
    assert len(by_name["example_run"]) == 60
    assert len(by_name["llm_call"]) == 60
    assert len(by_name["score"]) == 60

    suite_span = by_name["suite_run"][0]
    suite_ctx = suite_span.context

    for cat in by_name["category_run"]:
        assert cat.context.trace_id == suite_ctx.trace_id
        assert cat.parent is not None
        assert cat.parent.span_id == suite_ctx.span_id

    cat_span_ids = {c.context.span_id for c in by_name["category_run"]}
    for ex in by_name["example_run"]:
        assert ex.parent is not None
        assert ex.parent.span_id in cat_span_ids

    ex_span_ids = {e.context.span_id for e in by_name["example_run"]}
    for llm in by_name["llm_call"]:
        assert llm.parent is not None
        assert llm.parent.span_id in ex_span_ids

    for llm in by_name["llm_call"]:
        attrs = dict(llm.attributes)
        for required in (
            "model",
            "tokens_in",
            "tokens_out",
            "cost_usd",
            "latency_ms",
            "retry_count",
        ):
            assert required in attrs

    for ex in by_name["example_run"]:
        attrs = dict(ex.attributes)
        for required in ("category", "example_id", "gold_hash"):
            assert required in attrs


def test_suite_run_attributes(fresh_db, trace_handle) -> None:
    with db_module.session_scope() as session:
        run_suite(
            session,
            suite_root=SUITE_ROOT,
            suite_name="core_v1",
            suite_version="core_v1",
            provider=FakeProvider(),
            model="fake-large",
            categories=["classification"],
        )
    spans = trace_handle.finished_spans()
    suite_spans = [s for s in spans if s.name == "suite_run"]
    assert len(suite_spans) == 1
    attrs = dict(suite_spans[0].attributes)
    assert attrs["suite_name"] == "core_v1"
    assert attrs["model_version"] == "fake-large"
    assert attrs["n_examples"] == 10
