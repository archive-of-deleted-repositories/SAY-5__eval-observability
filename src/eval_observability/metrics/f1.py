"""Set-based F1 over normalized entity strings."""

from __future__ import annotations

from collections.abc import Iterable


def _normalize(items: Iterable[str]) -> set[str]:
    return {x.strip().lower() for x in items if x and x.strip()}


def entity_f1(predicted: Iterable[str], gold: Iterable[str]) -> tuple[float, float, float]:
    """Return (precision, recall, f1) over normalized entity sets."""
    pred = _normalize(predicted)
    gold_set = _normalize(gold)
    if not pred and not gold_set:
        return 1.0, 1.0, 1.0
    if not pred or not gold_set:
        return 0.0, 0.0, 0.0
    tp = len(pred & gold_set)
    precision = tp / len(pred)
    recall = tp / len(gold_set)
    f1 = 0.0 if (precision + recall) == 0 else 2 * precision * recall / (precision + recall)
    return precision, recall, f1
