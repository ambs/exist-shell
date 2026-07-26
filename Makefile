.PHONY: help ruff ty test checks

help: ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-8s %s\n", $$1, $$2}'

checks: ruff ty test ## Run ruff, ty and tests

test: ## Run tests
	uv run pytest

ruff: ## Lint with ruff
	uv run ruff check src/

ty: ## Type-check with ty
	uv run ty check src/ tests/
