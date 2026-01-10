#!/bin/bash
# Run FastAPI backend in development mode with proper environment variables

set -e

cd "$(dirname "$0")/.."

# Load .env file if it exists
if [ -f .env ]; then
    export $(grep -v '^#' .env | xargs)
fi

# Activate virtual environment
source .venv/bin/activate

# Run uvicorn with reload
PYTHONPATH=src uvicorn rlcoach.api.app:app --reload --port 8000
