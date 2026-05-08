"""``make bench-regress`` gate: per-category pass-rate drift check.

Runs the full ``core_v1`` suite against the FakeProvider, compares the result
against the committed ``eval/baselines/core_v1_fake.json``, and exits non-zero
if any category's pass rate drops by more than ``DRIFT_TOLERANCE`` (relative).

The CI workflow installs this script with ``poetry run python
-m scripts.bench_regress`` so the gate is hermetic and self-contained.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from eval_observability.db import create_all, session_scope
from eval_observability.obs.otel import configure_tracing
from eval_observability.providers.fake import FakeProvider
from eval_observability.runner import run_suite

REPO_ROOT = Path(__file__).resolve().parent.parent
SUITE_PATH = REPO_ROOT / "eval" / "suites" / "core_v1"
BASELINE_PATH = REPO_ROOT / "eval" / "baselines" / "core_v1_fake.json"

DRIFT_TOLERANCE = 0.30  # 30% relative drop on pass rate is the failure boundary.


def _load_baseline() -> dict[str, dict[str, float]]:
    raw = json.loads(BASELINE_PATH.read_text())
    return dict(raw["per_category"])


def main() -> int:
    configure_tracing(exporter="memory")
    create_all()
    with session_scope() as session:
        summary = run_suite(
            session,
            suite_root=SUITE_PATH,
            suite_name="core_v1",
            suite_version="core_v1",
            provider=FakeProvider(),
            model="fake-large",
        )

    baseline = _load_baseline()
    failures: list[str] = []
    rows: list[tuple[str, float, float, float]] = []
    for cat, stats in summary.per_category.items():
        prior = baseline.get(cat, {}).get("pass_rate")
        if prior is None:
            failures.append(f"{cat}: missing in baseline")
            continue
        current = stats["pass_rate"]
        drift = 0.0 if prior == 0.0 else (current - prior) / prior
        rows.append((cat, prior, current, drift))
        if drift < -DRIFT_TOLERANCE:
            failures.append(
                f"{cat}: pass_rate dropped {drift * 100:+.1f}% "
                f"(prior={prior:.4f} current={current:.4f}; "
                f"tolerance=-{DRIFT_TOLERANCE * 100:.0f}%)"
            )

    print(f"{'category':<24} {'prior':>10} {'current':>10} {'rel_drift':>12}")
    print("-" * 60)
    for cat, prior, current, drift in rows:
        print(f"{cat:<24} {prior:>10.4f} {current:>10.4f} {drift:>+11.2%}")

    if failures:
        print("\nbench-regress FAILED:", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        return 1
    print("\nbench-regress PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
