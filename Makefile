.PHONY: test fmt lint clean help install-dev rust-dev rust-build

# Default target
help:
	@echo "Available targets:"
	@echo "  test       - Run pytest with quiet flag"
	@echo "  fmt        - Format code with black"
	@echo "  lint       - Lint code with ruff"
	@echo "  clean      - Remove build artifacts and caches"
	@echo "  install-dev - Install development dependencies"
	@echo "  rust-dev   - Build/install Rust parser extension (maturin develop)"
	@echo "  rust-build - Build Rust wheel (release)"

# Install development dependencies
install-dev:
	pip install -e ".[dev]"
	@echo "Tip: run 'make rust-dev' to build the Rust parser extension."

# Run tests
test:
	PYTHONPATH=src pytest -q

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

# Build/install the Rust extension locally for development
rust-dev:
	python -m pip install --upgrade pip
	pip install maturin
	# Prefer maturin develop (editable install). If unavailable, build a wheel and pip install it.
	cd parsers/rlreplay_rust && (maturin develop || (maturin build -r && python -m pip install target/wheels/*.whl))
	python -c "import rlreplay_rust as m; print('RUST_CORE loaded:', getattr(m, 'RUST_CORE', False))"

# Build a release wheel for the Rust extension
rust-build:
	python -m pip install --upgrade pip
	pip install maturin
	cd parsers/rlreplay_rust && maturin build -r
