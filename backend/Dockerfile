# Backend Dockerfile for FastAPI + Python replay processing
FROM python:3.11-slim as base

# Install system dependencies for Rust compilation and replay parsing
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Rust for maturin builds
RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
ENV PATH="/root/.cargo/bin:${PATH}"

WORKDIR /app

# Copy dependency files first for better caching
COPY pyproject.toml ./
COPY src/rlcoach/__init__.py src/rlcoach/
COPY src/rlcoach/version.py src/rlcoach/

# Install Python dependencies
RUN pip install --no-cache-dir -e ".[dev]"

# Copy Rust parser source and build
COPY parsers/ parsers/
RUN cd parsers/rlreplay_rust && maturin develop --release || echo "Rust parser build skipped"

# Development stage
FROM base as development

COPY . .

# Create non-root user for development
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

ENV PYTHONPATH=/app/src
EXPOSE 8000

CMD ["uvicorn", "rlcoach.api.app:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

# Production stage
FROM base as production

# Copy application code
COPY src/ src/
COPY schemas/ schemas/
COPY alembic.ini ./
COPY migrations/ migrations/

# Create non-root user
RUN useradd -m -u 1000 appuser && \
    mkdir -p /app/storage /app/logs && \
    chown -R appuser:appuser /app

USER appuser

ENV PYTHONPATH=/app/src
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "rlcoach.api.app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
