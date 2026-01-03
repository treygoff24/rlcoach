# Worker Dockerfile for background replay processing
FROM python:3.11-slim as base

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Rust for maturin builds
RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
ENV PATH="/root/.cargo/bin:${PATH}"

WORKDIR /app

# Copy dependency files
COPY pyproject.toml setup.py ./
COPY src/rlcoach/__init__.py src/rlcoach/
COPY src/rlcoach/version.py src/rlcoach/

# Install Python dependencies including celery/rq
RUN pip install --no-cache-dir -e ".[dev]" celery[redis] rq

# Copy Rust parser source and build
COPY parsers/ parsers/
RUN cd parsers/rlreplay_rust && maturin develop --release || echo "Rust parser build skipped"

# Development stage
FROM base as development

COPY . .

RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

ENV PYTHONPATH=/app/src

CMD ["celery", "-A", "rlcoach.worker.tasks", "worker", "--loglevel=info", "--concurrency=4"]

# Production stage
FROM base as production

COPY src/ src/
COPY schemas/ schemas/

# Create non-root user with resource limits consideration
RUN useradd -m -u 1000 appuser && \
    mkdir -p /app/storage /app/logs && \
    chown -R appuser:appuser /app

USER appuser

ENV PYTHONPATH=/app/src
ENV PYTHONUNBUFFERED=1

# Worker configuration for replay processing
# Concurrency matches CPU cores, memory limited per task
CMD ["celery", "-A", "rlcoach.worker.tasks", "worker", \
     "--loglevel=info", \
     "--concurrency=4", \
     "--max-tasks-per-child=100", \
     "--time-limit=60", \
     "--soft-time-limit=30"]
