# Architecture

## Span hierarchy

A single `eval-obs run` invocation produces one trace whose root is `suite_run`. The full shape:

```
suite_run                           (attrs: suite_name, suite_version, model_version,
  │                                          started_at, n_examples, total_examples,
  │                                          total_passed)
  └── category_run                  (attrs: category, n_examples)
        └── example_run             (attrs: category, example_id, gold_hash, score, passed)
              ├── llm_call          (attrs: model, tokens_in, tokens_out, cost_usd,
              │                              latency_ms, retry_count)
              └── score             (attrs: metric_name, score, passed)
```

For the `core_v1` suite this expands to: 1 `suite_run` + 6 `category_run` + 60 `example_run` + 60 `llm_call` + 60 `score` = 187 spans.

Every error path keeps the parent `example_run` open and records a `Status(ERROR)` on the failing child span; the run as a whole is never aborted by a single failure.

## Trace-id correlated structured logging

The structlog pipeline runs `_otel_context_processor` *before* the JSON renderer. The processor reads the active span context via `opentelemetry.trace.get_current_span().get_span_context()` and, if valid, inlines:

```json
{"trace_id": "fbc0ed6a683f73318e2f2215a474f926", "span_id": "a1b2c3d4e5f60718", "category": "code", "example_id": "code-6", "level": "info", "event": "llm_call_failed"}
```

This is the design that makes log-trace correlation work without instrumenting every call site — the only requirement is that the log line is emitted *inside* a span. `tests/unit/test_log_trace_injection.py` asserts the field is present inside a span and absent outside.

## Welch's t-test vs naive delta

A naive "current_mean < prior_mean - 2pp" check trips on noise. Suite scores swing several percentage points between runs even with a deterministic provider (different examples can land in different windows depending on cron timing). Welch's two-sample t-test with unequal variances gives a principled p-value: large deltas with high within-window variance produce high p-values and don't fire; small deltas with tight within-window variance can fire. We require both: `delta < -2pp` AND `p < 0.05`.

The implementation is pure Python (`src/eval_observability/regression/stats.py`) using:
- Welch-Satterthwaite degrees of freedom
- Lentz's continued-fraction expansion for the regularized incomplete beta function `I_x(a, b)`
- Two-sided survival function via the Student's t CDF

`tests/unit/test_welch_ttest_vs_scipy.py` runs 20 randomized seed cases against `scipy.stats.ttest_ind(equal_var=False)` and asserts agreement to `abs=1e-4` on both the t-statistic and the p-value.

## Idempotent daily-report design

`generate_daily_report` is keyed on `(suite_id, model_version, date(now))`. The first call inserts a `daily_reports` row; subsequent calls on the same UTC date return the existing row without re-running the t-tests. This matters because the cron is wired to run hourly by default — the natural frequency for catching mid-day model rollouts — and we don't want every hour to spawn a new file.

The `RegressionAlert` rows, on the other hand, are *not* deduped per day. If the t-test detects a regression on the same `(suite, model, category)` for two days running, two alert rows are inserted — by design, so dashboards can plot how long an alert has persisted.

## Hermetic-trace testing pattern

Real eval pipelines have to ship traces somewhere — Jaeger, Tempo, an OTel collector, etc. CI shouldn't depend on any of that. The `obs/otel.py` module configures the SDK with one of three exporters at runtime:

- `memory` — `InMemorySpanExporter` keeps finished spans on a Python list; tests read it directly. (Used by every test except integration.)
- `stdout` — `ConsoleSpanExporter` emits each span as a printed dict; useful for local debugging.
- `otlp` — `OTLPSpanExporter` over gRPC; what production deployments use.

The `InMemoryExporterHandle` returned by `configure_tracing(exporter="memory")` exposes `.finished_spans()` and `.clear()` so a test can do:

```python
def test_full_suite_span_tree(fresh_db, trace_handle):
    # ... run suite ...
    spans = trace_handle.finished_spans()
    by_name = group_by_name(spans)
    assert len(by_name["suite_run"]) == 1
    assert len(by_name["example_run"]) == 60
    cat_ids = {c.context.span_id for c in by_name["category_run"]}
    for ex in by_name["example_run"]:
        assert ex.parent.span_id in cat_ids
```

This pattern catches regressions in the span graph (e.g., an `await` that breaks context propagation) without needing a Jaeger sidecar.

## The OTel set-once gotcha

`opentelemetry.trace.set_tracer_provider` uses a `_TRACER_PROVIDER_SET_ONCE` guard — call it twice and the second call is silently ignored, with the warning *"Overriding of current TracerProvider is not allowed"*. That makes test isolation awkward.

The framework's workaround: hold a module-level reference to the `TracerProvider` we created. On each `configure_tracing` call we (a) drop the previous span processors via `processor.shutdown()`, then (b) install the new exporter as a fresh processor on the *same* provider. Tests obtain their tracer via `get_tracer()`, which prefers the module-local provider over the global. Tests don't have to worry about the set-once guard at all.

## Database schema

Five tables — three are ledger-style append-only.

```
suites              (id, name, version, manifest_hash, created_at)
                    UNIQUE (name, version)

runs                (id, suite_id FK, model_version, started_at, finished_at,
                     status, summary jsonb, otel_trace_id)

run_items           (id, run_id FK, category, example_id, output_text, score,
                     passed, latency_ms, cost_usd, span_id, status, error,
                     details jsonb)

regression_alerts   (id, suite_id FK, model_version, category, current_mean,
                     prior_mean, delta, p_value, detected_at)

daily_reports       (id, suite_id FK, model_version, date, file_path,
                     summary jsonb, generated_at)
                    UNIQUE (suite_id, model_version, date)
```

`runs.otel_trace_id` is the link back into Tempo/Jaeger. `run_items.span_id` lets the cron join an alert back to the specific failing example.

The `summary` JSONB columns hold the rendered per-category numbers — denormalised on purpose, because regenerating them from `run_items` for every cron pass adds a non-trivial fan-out join.

## What's deliberately not here

- **Streaming evals.** The framework is run-driven. Hooking it up to a queue is left to the operator.
- **Provider retry/back-off logic.** `ChatProvider.chat` is a single call; retries are the provider's responsibility.
- **Cost tracking beyond a single number.** `cost_usd` is recorded per item; we don't try to model token-class pricing tiers — providers report what they report.
- **Cross-trace correlation in tests.** Tests verify within-trace shape; they don't make assertions about the OTLP exporter's wire format.
- **Distributed cron locking.** APScheduler is configured for a single process. A real production deploy would put the cron behind a leader-elected lock.
- **A web UI.** That's `SAY-5/genai-eval`.
