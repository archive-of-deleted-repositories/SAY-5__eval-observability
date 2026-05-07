"""Case-insensitive exact-match metric."""

from __future__ import annotations


def exact_match(prediction: str, gold: str) -> float:
    return 1.0 if prediction.strip().lower() == gold.strip().lower() else 0.0
