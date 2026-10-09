.PHONY: install test test-unit test-contract test-smoke

install:
	pip install -e ".[dev]"

test:
	pytest

test-unit:
	pytest tests/unit

test-contract:
	pytest tests/contract

test-smoke:
	pytest tests/smoke
