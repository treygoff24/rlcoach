.PHONY: test test-cov fmt lint clean help install-dev rust-dev rust-build require-venv

VENV_BIN := $(CURDIR)/.venv/bin
VENV_PY := $(VENV_BIN)/python
PIP := $(VENV_PY) -m pip
PYTEST := $(VENV_PY) -m pytest
BLACK := $(VENV_PY) -m black
RUFF := $(VENV_PY) -m ruff
MATURIN := $(VENV_PY) -m maturin

require-venv:
	@test -x "$(VENV_PY)" || { \
		echo "error: .venv is required for Python targets. Create it and install deps before running make." >&2; \
		exit 1; \
	}

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
install-dev: require-venv
	$(PIP) install -e ".[dev]"
	@echo "Tip: run 'make rust-dev' to build the Rust parser extension."

# Run tests
test: require-venv
	PYTHONPATH=src $(PYTEST) -q

# Run tests with coverage (overall + per-category threshold gate)
test-cov: require-venv
	PYTHONPATH=src $(PYTEST) -q --cov=src/rlcoach --cov-report=term-missing --cov-report=json:coverage.json --cov-report=xml:coverage.xml
	$(VENV_PY) scripts/check_coverage_categories.py --json coverage.json --threshold 50

# Format code
fmt: require-venv
	$(BLACK) src/ tests/

# Lint code
lint: require-venv
	$(RUFF) check src/ tests/

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
rust-dev: require-venv
	$(PIP) install --upgrade pip
	$(PIP) install maturin
	# Prefer maturin develop (editable install). If unavailable, build a wheel and pip install it.
	cd parsers/rlreplay_rust && ( \
		$(MATURIN) develop || { \
			rm -rf target/rlcoach-wheels && \
			mkdir -p target/rlcoach-wheels && \
			$(MATURIN) build -r --out target/rlcoach-wheels && \
			wheel_count=$$(find target/rlcoach-wheels -maxdepth 1 -type f -name '*.whl' | wc -l | tr -d ' ') && \
			if [ "$$wheel_count" != "1" ]; then \
				echo "error: expected exactly one wheel in target/rlcoach-wheels, found $$wheel_count" >&2; \
				exit 1; \
			fi && \
			wheel=$$(find target/rlcoach-wheels -maxdepth 1 -type f -name '*.whl' -print -quit) && \
			$(PIP) install "$$wheel"; \
		} \
	)
	$(VENV_PY) -c "import rlreplay_rust as m; print('RUST_CORE loaded:', getattr(m, 'RUST_CORE', False))"

# Build a release wheel for the Rust extension
rust-build: require-venv
	$(PIP) install --upgrade pip
	$(PIP) install maturin
	cd parsers/rlreplay_rust && $(MATURIN) build -r
