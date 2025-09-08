.PHONY: test fmt lint clean help install-dev

# Default target
help:
	@echo "Available targets:"
	@echo "  test       - Run pytest with quiet flag"
	@echo "  fmt        - Format code with black"
	@echo "  lint       - Lint code with ruff"
	@echo "  clean      - Remove build artifacts and caches"
	@echo "  install-dev - Install development dependencies"

# Install development dependencies
install-dev:
	pip install -e ".[dev]"

# Run tests
test:
	pytest -q

# Format code
fmt:
	black src/ tests/

# Lint code
lint:
	ruff check src/ tests/

# Clean build artifacts
clean:
	rm -rf build/
	rm -rf dist/
	rm -rf *.egg-info/
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	rm -rf .pytest_cache/
	rm -rf .coverage
	rm -rf htmlcov/