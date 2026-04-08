#!/usr/bin/env sh
set -eu

if [ ! -x ".venv/bin/python" ]; then
  echo "Missing .venv/bin/python; create the project virtualenv before running mission workers." >&2
  exit 1
fi

if [ ! -f ".env" ] && [ -f ".env.example" ]; then
  cp .env.example .env
fi

# Preflight only; do not install packages or start services here.
.venv/bin/python --version >/dev/null
if command -v cargo >/dev/null 2>&1; then
  cargo --version >/dev/null
fi
if [ -x ".venv/bin/maturin" ]; then
  .venv/bin/maturin --version >/dev/null
fi
