"""``otel-smoke`` integration: live OTLP exporter -> otel-collector -> stdout.

This script is the body of the CI ``otel-smoke`` job. It assumes the
``otel-collector`` container is already up (the job spins it via
``docker compose up -d otel-collector jaeger``) and reachable on
``localhost:4317``.

The script:

  1. Configures tracing in ``OTEL_MODE=otlp`` mode and runs a small eval
     (one category, two examples) so the collector receives a real-shaped
     span tree.
  2. Forces a flush via the ``BatchSpanProcessor`` shutdown so all spans
     reach the collector before we read its stdout.
  3. Pulls the collector's stdout via ``docker compose logs otel-collector``,
     greps for the ``Name :`` lines emitted by the ``debug`` exporter at
     ``verbosity: detailed``, and asserts the expected hierarchy
     (1 suite_run + 1 category_run + N example_run + N llm_call + N score).

Exits 0 on success and prints the parsed span tree.
"""

from __future__ import annotations

import re
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

from eval_observability.db import create_all, session_scope
from eval_observability.obs.otel import _processors, configure_tracing
from eval_observability.providers.fake import FakeProvider
from eval_observability.runner import run_suite

REPO_ROOT = Path(__file__).resolve().parent.parent
SUITE_PATH = REPO_ROOT / "eval" / "suites" / "core_v1"

N_EXAMPLES = 2  # Per category. Smoke job only exercises one category to stay fast.
CATEGORY = "extraction"
COLLECTOR_SERVICE = "otel-collector"

# The ``debug`` exporter at ``verbosity: detailed`` emits one section per span,
# starting with a line of the form: ``Span #N`` followed by ``    Name        : llm_call``
_NAME_RE = re.compile(r"Name\s*:\s*(\w+)")


def _flush_processors() -> None:
    """Force-flush every attached span processor and shut them down so the
    collector sees the spans before we sample its stdout.
    """
    for proc in _processors:
        try:
            proc.force_flush(timeout_millis=5_000)
        except Exception:  # noqa: BLE001
            pass
        try:
            proc.shutdown()
        except Exception:  # noqa: BLE001
            pass


def _collector_logs() -> str:
    out = subprocess.run(  # noqa: S603,S607
        ["docker", "compose", "logs", "--no-color", COLLECTOR_SERVICE],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    return out.stdout


def _read_collector_span_names(timeout_s: float = 30.0) -> list[str]:
    """Poll the collector's stdout (via ``docker compose logs``) until the
    expected span count appears or we time out.
    """
    expected_total = 1 + 1 + N_EXAMPLES * 3  # suite + category + (example, llm_call, score)
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        text = _collector_logs()
        names = _NAME_RE.findall(text)
        if len(names) >= expected_total:
            return names
        time.sleep(1.0)
    raise TimeoutError(
        f"otel-smoke: collector stdout did not contain >= {expected_total} "
        f"`Name : ...` lines within {timeout_s:.0f}s"
    )


def main() -> int:
    configure_tracing(exporter="otlp", otlp_endpoint="http://localhost:4317")
    create_all()
    with session_scope() as session:
        summary = run_suite(
            session,
            suite_root=SUITE_PATH,
            suite_name="core_v1",
            suite_version="core_v1",
            provider=FakeProvider(),
            model="fake-large",
            categories=[CATEGORY],
            limit=N_EXAMPLES,
        )

    _flush_processors()
    names = _read_collector_span_names()

    counts = Counter(names)
    print("collector span tree (from `docker compose logs otel-collector`):")
    for name in ("suite_run", "category_run", "example_run", "llm_call", "score"):
        print(f"  {name:<14} {counts.get(name, 0)}")

    expected = {
        "suite_run": 1,
        "category_run": 1,
        "example_run": N_EXAMPLES,
        "llm_call": N_EXAMPLES,
        "score": N_EXAMPLES,
    }
    failures: list[str] = []
    for name, want in expected.items():
        got = counts.get(name, 0)
        if got < want:
            failures.append(f"{name}: got {got}, expected >= {want}")
    if failures:
        print("\notel-smoke FAILED:", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        return 1
    print(f"\notel-smoke PASSED  trace_id={summary.trace_id}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
