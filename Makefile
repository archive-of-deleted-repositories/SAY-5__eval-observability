.PHONY: dev migrate seed test test-cov lint typecheck eval eval-smoke cron-daily report-list up down clean format synth bench-regress

PY ?= poetry run

dev:
	poetry install --with dev

migrate:
	$(PY) alembic upgrade head

seed:
	$(PY) python -m eval_observability.cli seed

test:
	$(PY) pytest tests/unit tests/trace -v

test-cov:
	$(PY) pytest tests/unit tests/trace --cov=src/eval_observability --cov-report=term-missing

lint:
	$(PY) ruff check src tests
	$(PY) black --check src tests

format:
	$(PY) ruff check --fix src tests
	$(PY) black src tests

typecheck:
	$(PY) mypy

eval:
	$(PY) eval-obs run --suite core_v1 --provider fake --model fake-large

eval-smoke:
	$(PY) eval-obs run --suite core_v1 --provider fake --model fake-large --smoke

synth:
	$(PY) python -m eval.synth.synthesize

bench-regress:
	$(PY) python -m scripts.bench_regress

cron-daily:
	$(PY) eval-obs cron daily --suite core_v1 --model fake-large

report-list:
	$(PY) eval-obs report list --since 7d

up:
	docker compose up -d

down:
	docker compose down

clean:
	rm -rf .pytest_cache .mypy_cache .ruff_cache .coverage dist build *.egg-info
	find . -type d -name __pycache__ -exec rm -rf {} +
