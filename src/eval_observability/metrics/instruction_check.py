"""Constraint-satisfaction scoring for instruction-following examples."""

from __future__ import annotations

import json
import re
from typing import Any

_SENTENCE_RE = re.compile(r"[^.!?]+[.!?]")


def _count_sentences(text: str) -> int:
    return len([s for s in _SENTENCE_RE.findall(text) if s.strip()])


def check_instruction(prediction: str, constraints: dict[str, Any]) -> dict[str, Any]:
    """Score a prediction against a constraint spec.

    Constraint keys (all optional):
      - ``json_only``: bool. Prediction must parse as JSON.
      - ``required_keys``: list[str]. JSON object must contain these keys.
      - ``forbidden_keys``: list[str]. JSON object must NOT contain these keys.
      - ``sentence_count``: dict {field: int}. Exact sentence count for the
        named field's value.
      - ``value_types``: dict {field: type-name}. e.g. {"C": "int"}.

    Returns a dict with overall ``score`` (fraction of satisfied checks),
    ``passed`` (all checks satisfied), and per-check ``details``.
    """
    checks: list[tuple[str, bool]] = []
    details: dict[str, Any] = {}

    parsed: Any = None
    if constraints.get("json_only"):
        try:
            parsed = json.loads(prediction)
            checks.append(("json_only", True))
        except (ValueError, TypeError):
            checks.append(("json_only", False))
            details["json_error"] = True
            score = 0.0
            return {"score": score, "passed": False, "details": details, "checks": checks}

    if isinstance(parsed, dict):
        for key in constraints.get("required_keys", []):
            present = key in parsed
            checks.append((f"required:{key}", present))

        for key in constraints.get("forbidden_keys", []):
            absent = key not in parsed
            checks.append((f"forbidden:{key}", absent))

        for field, expected_count in constraints.get("sentence_count", {}).items():
            value = parsed.get(field, "")
            actual = _count_sentences(str(value))
            checks.append((f"sentences:{field}={expected_count}", actual == expected_count))
            details[f"sentences_{field}"] = actual

        for field, type_name in constraints.get("value_types", {}).items():
            value = parsed.get(field)
            ok = (
                (type_name == "int" and isinstance(value, int) and not isinstance(value, bool))
                or (type_name == "str" and isinstance(value, str))
                or (type_name == "float" and isinstance(value, int | float))
            )
            checks.append((f"type:{field}={type_name}", bool(ok)))

    if not checks:
        return {"score": 1.0, "passed": True, "details": details, "checks": checks}

    passed_count = sum(1 for _, ok in checks if ok)
    score = passed_count / len(checks)
    return {
        "score": score,
        "passed": passed_count == len(checks),
        "details": details,
        "checks": checks,
    }
