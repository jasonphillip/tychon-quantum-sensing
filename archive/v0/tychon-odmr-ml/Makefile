.PHONY: test test-unit test-contract test-smoke install clean snapshot

test:
	python -m pytest tests/ -v

test-unit:
	python -m pytest tests/unit/ -v

test-contract:
	python -m pytest tests/contract/ -v

test-smoke:
	python -m pytest tests/smoke/ -v

install:
	pip install -e ".[dev]"

clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type d -name "*.egg-info" -exec rm -rf {} +
	rm -rf dist/ build/

snapshot:
	bash scripts/generate_repo_snapshot.sh
