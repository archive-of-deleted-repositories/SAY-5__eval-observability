"""Synthesize 90 additional examples per category (10 -> 100, total -> 600).

Every category gets:
  * a deterministic pool of synthesized prompts seeded with ``Faker(SEED)`` and
    ``random.Random(SEED)``
  * a paired set of "fake" answers — the FakeProvider looks them up by the
    synthesized example_id. Roughly ``WRONG_RATE`` of the synthesized answers
    are intentionally incorrect, so the resulting pass rates land in a
    reasonable mid-range and stress every metric's failure path.

The output:

  1. ``eval/suites/core_v1/<category>.yaml`` — appended in place
  2. ``src/eval_observability/providers/_synth_answers.py`` — generated module
     containing the answer table + a marker line telling humans not to edit it.

Run with::

    poetry run python -m eval.synth.synthesize
"""

from __future__ import annotations

import json
import random
from pathlib import Path

import yaml
from faker import Faker

SEED = 42
TARGET_PER_CATEGORY = 100
WRONG_RATE = 0.2  # ~20% of synthesized answers are wrong on purpose.

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SUITE_ROOT = REPO_ROOT / "eval" / "suites" / "core_v1"
ANSWERS_FILE = REPO_ROOT / "src" / "eval_observability" / "providers" / "_synth_answers.py"

CATEGORY_ORDER = [
    "extraction",
    "classification",
    "summarization",
    "reasoning",
    "code",
    "instruction_following",
]


# --------------------------------------------------------------------------- #
# Per-category synthesizers. Each returns ``(new_examples, fake_answers)``.   #
# new_examples is a list of dict shaped like the existing yaml entries.        #
# fake_answers maps example_id -> response text.                               #
# --------------------------------------------------------------------------- #


def _ent_id(prefix: str, n: int) -> str:
    return f"{prefix}-syn-{n:03d}"


def synth_extraction(faker: Faker, rng: random.Random) -> tuple[list[dict], dict[str, str]]:
    examples: list[dict] = []
    answers: dict[str, str] = {}
    n_to_add = TARGET_PER_CATEGORY - 10
    for n in range(1, n_to_add + 1):
        person = faker.name()
        city = faker.city()
        country = faker.country()
        thing = faker.word().capitalize()
        passage = f"{person} traveled from {city} in {country} to study {thing}."
        gold = [person, city, country, thing]
        ex_id = _ent_id("extraction", n)
        examples.append(
            {
                "id": ex_id,
                "input": passage,
                "gold": {"entities": gold},
            }
        )
        if rng.random() < WRONG_RATE:
            # Drop one entity to fail the precision/recall check.
            wrong = gold[:-1]
            answers[ex_id] = json.dumps({"entities": wrong})
        else:
            answers[ex_id] = json.dumps({"entities": gold})
    return examples, answers


_LABELS = ["positive", "negative", "neutral"]
_CL_TEMPLATES = {
    "positive": [
        "Loved this — {adj}!",
        "Easily the best {noun} I've used in years.",
        "Exceeded my expectations on every front.",
        "Will definitely buy again. {adj}.",
    ],
    "negative": [
        "Awful experience. {noun} broke after one use.",
        "Terrible service and {adj} food.",
        "Worst {noun} I've ever owned.",
        "Would not recommend to anyone — {adj}.",
    ],
    "neutral": [
        "It's okay. {adj}, nothing special.",
        "An average {noun}. Does what it says.",
        "Fine for the price; nothing memorable.",
        "Not great, not bad — just {adj}.",
    ],
}


def synth_classification(faker: Faker, rng: random.Random) -> tuple[list[dict], dict[str, str]]:
    examples: list[dict] = []
    answers: dict[str, str] = {}
    n_to_add = TARGET_PER_CATEGORY - 10
    for n in range(1, n_to_add + 1):
        label = rng.choice(_LABELS)
        template = rng.choice(_CL_TEMPLATES[label])
        text = template.format(adj=faker.word(), noun=faker.word())
        ex_id = _ent_id("classification", n)
        examples.append({"id": ex_id, "input": text, "gold": label})
        if rng.random() < WRONG_RATE:
            wrong_label = rng.choice([lab for lab in _LABELS if lab != label])
            answers[ex_id] = wrong_label
        else:
            answers[ex_id] = label
    return examples, answers


def synth_summarization(faker: Faker, rng: random.Random) -> tuple[list[dict], dict[str, str]]:
    examples: list[dict] = []
    answers: dict[str, str] = {}
    n_to_add = TARGET_PER_CATEGORY - 10
    for n in range(1, n_to_add + 1):
        topic = faker.word().capitalize()
        verb = faker.word()
        a = faker.sentence(nb_words=12)
        b = faker.sentence(nb_words=12)
        passage = f"{topic} is a concept that often {verb}s. {a} {b}"
        # Reference summary embeds the same head tokens so ROUGE-L hits the
        # passing threshold (>=0.5) for the "right" answers.
        reference = f"{topic} is a concept that often {verb}s and is described in the passage."
        ex_id = _ent_id("summarization", n)
        examples.append({"id": ex_id, "input": passage, "gold": reference})
        if rng.random() < WRONG_RATE:
            answers[ex_id] = "A completely different and irrelevant sentence about quasars."
        else:
            answers[ex_id] = reference
    return examples, answers


def synth_reasoning(faker: Faker, rng: random.Random) -> tuple[list[dict], dict[str, str]]:
    examples: list[dict] = []
    answers: dict[str, str] = {}
    n_to_add = TARGET_PER_CATEGORY - 10
    for n in range(1, n_to_add + 1):
        a = rng.randint(2, 50)
        b = rng.randint(2, 50)
        op_idx = rng.randint(0, 2)
        if op_idx == 0:
            problem = f"Compute {a} plus {b}."
            answer = a + b
        elif op_idx == 1:
            problem = f"Multiply {a} by {b}."
            answer = a * b
        else:
            problem = f"Compute {a + b} minus {a}."
            answer = b
        ex_id = _ent_id("reasoning", n)
        examples.append(
            {
                "id": ex_id,
                "input": problem,
                "gold": {"answer": str(answer), "expected_steps": 1},
            }
        )
        if rng.random() < WRONG_RATE:
            # Skip CoT — fails because correct AND has_cot are required.
            answers[ex_id] = f"Answer: {answer}"
        else:
            answers[ex_id] = f"Step 1: doing the math. Answer: {answer}"
    return examples, answers


def synth_code(faker: Faker, rng: random.Random) -> tuple[list[dict], dict[str, str]]:
    """Tiny pure-arithmetic functions so subprocess pytest stays fast.

    Each example is one of three templates (square, double, halve_int) so the
    generated code body is trivial and deterministic.
    """
    examples: list[dict] = []
    answers: dict[str, str] = {}
    n_to_add = TARGET_PER_CATEGORY - 10
    for n in range(1, n_to_add + 1):
        kind = rng.randint(0, 2)
        ex_id = _ent_id("code", n)
        if kind == 0:
            sig = 'def square(n: int) -> int:\n    """Return n squared."""\n'
            tests = (
                "def test_basic():\n"
                "    assert square(0) == 0\n"
                "    assert square(3) == 9\n"
                "    assert square(-4) == 16\n"
            )
            correct_impl = "def square(n):\n    return n * n\n"
            wrong_impl = "def square(n):\n    return n + n\n"
            fname = "square"
        elif kind == 1:
            sig = 'def double(n: int) -> int:\n    """Return 2n."""\n'
            tests = (
                "def test_basic():\n"
                "    assert double(0) == 0\n"
                "    assert double(3) == 6\n"
                "    assert double(-2) == -4\n"
            )
            correct_impl = "def double(n):\n    return n * 2\n"
            wrong_impl = "def double(n):\n    return n + 2\n"
            fname = "double"
        else:
            sig = 'def halve_int(n: int) -> int:\n    """Return n // 2."""\n'
            tests = (
                "def test_basic():\n"
                "    assert halve_int(0) == 0\n"
                "    assert halve_int(4) == 2\n"
                "    assert halve_int(7) == 3\n"
            )
            correct_impl = "def halve_int(n):\n    return n // 2\n"
            wrong_impl = "def halve_int(n):\n    return n / 2\n"
            fname = "halve_int"
        examples.append(
            {
                "id": ex_id,
                "input": sig,
                "gold": {"function_name": fname, "tests": tests},
            }
        )
        answers[ex_id] = wrong_impl if rng.random() < WRONG_RATE else correct_impl
    return examples, answers


def synth_instruction_following(
    faker: Faker, rng: random.Random
) -> tuple[list[dict], dict[str, str]]:
    examples: list[dict] = []
    answers: dict[str, str] = {}
    n_to_add = TARGET_PER_CATEGORY - 10
    for n in range(1, n_to_add + 1):
        word_a = faker.word()
        c_int = rng.randint(0, 99)
        prompt = (
            "Reply with a JSON object having keys A (string), B (string with "
            "exactly 3 sentences), and C (integer)."
        )
        gold = {
            "json_only": True,
            "required_keys": ["A", "B", "C"],
            "sentence_count": {"B": 3},
            "value_types": {"A": "str", "C": "int"},
        }
        ex_id = _ent_id("instruction_following", n)
        examples.append({"id": ex_id, "input": prompt, "gold": gold})
        # Correct answer: 3-sentence string + valid types.
        good = json.dumps({"A": word_a, "B": "First. Second. Third.", "C": c_int})
        # Wrong: drop key C — fails required_keys.
        bad = json.dumps({"A": word_a, "B": "First. Second. Third."})
        answers[ex_id] = bad if rng.random() < WRONG_RATE else good
    return examples, answers


SYNTHESIZERS = {
    "extraction": synth_extraction,
    "classification": synth_classification,
    "summarization": synth_summarization,
    "reasoning": synth_reasoning,
    "code": synth_code,
    "instruction_following": synth_instruction_following,
}


# --------------------------------------------------------------------------- #
# Drivers                                                                      #
# --------------------------------------------------------------------------- #


def _strip_synth_examples(yaml_doc: dict) -> dict:
    """Remove any prior ``-syn-`` entries so re-running is idempotent."""
    yaml_doc["examples"] = [
        ex for ex in yaml_doc.get("examples", []) if "-syn-" not in str(ex.get("id", ""))
    ]
    return yaml_doc


def synthesize_all() -> dict[str, dict[str, str]]:
    """Walk every category, append synthesized examples in place, return the
    full flat ``example_id -> answer`` table that the FakeProvider wires up.
    """
    full_answers: dict[str, dict[str, str]] = {}
    for category in CATEGORY_ORDER:
        # Fresh seeded sources per category so per-category content is stable
        # even if categories are added/removed/reordered.
        faker = Faker()
        Faker.seed(SEED)
        rng = random.Random(SEED)
        path = SUITE_ROOT / f"{category}.yaml"
        doc = yaml.safe_load(path.read_text())
        doc = _strip_synth_examples(doc)
        new_examples, answers = SYNTHESIZERS[category](faker, rng)
        doc["examples"].extend(new_examples)
        path.write_text(yaml.safe_dump(doc, sort_keys=False, allow_unicode=True))
        full_answers[category] = answers
    _write_answers_module(full_answers)
    return full_answers


def _write_answers_module(answers: dict[str, dict[str, str]]) -> None:
    """Emit the answer dict as a Python module imported by FakeProvider."""
    flat: dict[str, str] = {}
    for cat in CATEGORY_ORDER:
        flat.update(answers[cat])
    body = (
        '"""Auto-generated by eval/synth/synthesize.py. Do not hand-edit.\n\n'
        "Maps synthesized example_id -> the canned response that the\n"
        "``FakeProvider`` returns. Re-run ``poetry run python -m "
        'eval.synth.synthesize`` to regenerate after editing the synthesizer.\n"""\n\n'
        "from __future__ import annotations\n\n"
        "SYNTH_ANSWERS: dict[str, str] = {\n"
    )
    for k in sorted(flat):
        body += f"    {k!r}: {flat[k]!r},\n"
    body += "}\n"
    ANSWERS_FILE.write_text(body)


if __name__ == "__main__":
    synthesize_all()
    print(f"synthesized {TARGET_PER_CATEGORY * len(CATEGORY_ORDER)} examples total")
