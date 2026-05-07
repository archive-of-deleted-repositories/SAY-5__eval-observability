"""Per-category suite loaders and scoring functions."""

from . import (
    classification,
    code,
    extraction,
    instruction_following,
    reasoning,
    summarization,
)
from ._base import CategoryModule, Example, ScoreResult

CATEGORIES: dict[str, CategoryModule] = {
    "extraction": extraction,
    "classification": classification,
    "summarization": summarization,
    "reasoning": reasoning,
    "code": code,
    "instruction_following": instruction_following,
}

__all__ = ["CATEGORIES", "CategoryModule", "Example", "ScoreResult"]
