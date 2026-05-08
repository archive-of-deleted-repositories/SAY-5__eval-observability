"""Faker-driven suite synthesis for eval-observability.

The :mod:`eval.synth.synthesize` module grows each of the six core_v1
categories from 10 to 100 examples. The output is **deterministic** because
every call site seeds ``Faker(SEED)`` and ``random.Random(SEED)`` before any
generation, so the same suite hashes on every run.
"""
