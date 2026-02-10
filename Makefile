.PHONY: test test-cov fmt lint clean help install-dev rust-dev rust-build

# Virtual environment activation helper
# If .venv exists, run commands within it
# Use absolute path so it works from subdirectories (e.g., cd parsers/...)
VENV_BIN := $(if $(wildcard .venv/bin/python),$(CURDIR)/.venv/bin/,)

# Default target
help:
	@echo "Available targets:"
	@echo "  test       - Run pytest with quiet flag"
	@echo "  test-cov   - Run pytest with coverage report and category checks"
	@echo "  fmt        - Format code with black"
	@echo "  lint       - Lint code with ruff"
	@echo "  clean      - Remove build artifacts and caches"
	@echo "  install-dev - Install development dependencies"
	@echo "  rust-dev   - Build/install Rust parser extension (maturin develop)"
	@echo "  rust-build - Build Rust wheel (release)"

# Install development dependencies
install-dev:
	$(VENV_BIN)pip install -e ".[dev]"
	@echo "Tip: run 'make rust-dev' to build the Rust parser extension."

# Run tests
test:
	PYTHONPATH=src $(VENV_BIN)pytest -q

# Run tests with coverage (overall + per-category threshold gate)
test-cov:
	PYTHONPATH=src $(VENV_BIN)pytest -q --cov=src/rlcoach --cov-report=term-missing --cov-report=json:coverage.json --cov-report=xml:coverage.xml
	$(VENV_BIN)python scripts/check_coverage_categories.py --json coverage.json --threshold 50

# Format code
fmt:
	$(VENV_BIN)black src/ tests/

# Lint code
lint:
	$(VENV_BIN)ruff check src/ tests/

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

# Build/install the Rust extension locally for development
rust-dev:
	$(VENV_BIN)python -m pip install --upgrade pip
	$(VENV_BIN)pip install maturin
	# Prefer maturin develop (editable install). If unavailable, build a wheel and pip install it.
	cd parsers/rlreplay_rust && ($(VENV_BIN)maturin develop || ($(VENV_BIN)maturin build -r && $(VENV_BIN)python -m pip install target/wheels/*.whl))
	$(VENV_BIN)python -c "import rlreplay_rust as m; print('RUST_CORE loaded:', getattr(m, 'RUST_CORE', False))"

# Build a release wheel for the Rust extension
rust-build:
	$(VENV_BIN)python -m pip install --upgrade pip
	$(VENV_BIN)pip install maturin
	cd parsers/rlreplay_rust && $(VENV_BIN)maturin build -r
