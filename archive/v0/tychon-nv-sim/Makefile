.PHONY: install test smoke lint format clean lock snapshot

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

snapshot:
	./scripts/generate_repo_snapshot.sh

clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type d -name "*.egg-info" -exec rm -rf {} +
