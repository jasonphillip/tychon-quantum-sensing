.PHONY: install install-orbit orbit-wheels test smoke lint format clean lock

install:
	pip install -e ".[dev]"

install-orbit:
	pip install -e ".[orbit]"

# Pre-stage manylinux2014_aarch64 wheels for air-gapped DGX Spark targets.
# Run on a connected box, then sync wheels/orbit/ to each Spark and install
# with: pip install --no-index --find-links wheels/orbit sgp4 ppigrf
orbit-wheels:
	mkdir -p wheels/orbit
	pip download \
		--platform manylinux2014_aarch64 \
		--python-version 3.11 \
		--only-binary=:all: \
		-d wheels/orbit \
		sgp4 ppigrf

test:
	python -m pytest tests/ -v

smoke:
	python -m pytest tests/smoke/ -v -m smoke

lint:
	ruff check src/ tests/
	ruff format --check src/ tests/

format:
	ruff format src/ tests/

lock:
	.venv/bin/pip freeze > requirements.lock

clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type d -name "*.egg-info" -exec rm -rf {} +
