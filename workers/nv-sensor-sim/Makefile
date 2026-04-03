.PHONY: install test smoke lint format clean lock

install:
	pip install -e ".[dev]"

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
