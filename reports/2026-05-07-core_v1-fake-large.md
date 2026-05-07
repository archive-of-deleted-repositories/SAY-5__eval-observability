# core_v1/core_v1 — fake-large — 2026-05-07

## Summary

| category | current_mean | prior_mean | delta | p_value | regression |
|---|---|---|---|---|---|
| classification | 0.8000 | 0.8488 | -0.0487 | 0.7231 | no |
| code | 0.8000 | 0.8488 | -0.0487 | 0.7231 | no |
| extraction | 0.9457 | 0.9888 | -0.0430 | 0.1600 | no |
| instruction_following | 0.9600 | 0.9688 | -0.0088 | 0.7506 | no |
| reasoning | 0.9000 | 0.9288 | -0.0288 | 0.7803 | no |
| summarization | 0.3925 | 0.6188 | -0.2263 | 0.0059 | yes |

## Regressions flagged

- **summarization**: -22.63pp (p=0.0059) current=0.3925 prior=0.6188

## Notes

- Window: 7-day current vs prior 7-day window ending 2026-05-07T09:44:56.996716+00:00.
- Threshold: delta < -0.020 AND p < 0.050.
- Trace links: see Postgres `runs.otel_trace_id` for individual traces.
