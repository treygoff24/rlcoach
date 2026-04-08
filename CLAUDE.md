# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Virtual Environment (CRITICAL)

All Python commands MUST activate the venv first. System Python has no packages installed.

```bash
source .venv/bin/activate && <command>
```

## Build & Test Commands

```bash
# Backend
source .venv/bin/activate && PYTHONPATH=src pytest -q              # all tests
source .venv/bin/activate && PYTHONPATH=src pytest tests/test_foo.py -q  # single file
source .venv/bin/activate && ruff check src/ tests/                # lint
source .venv/bin/activate && black --check src/ tests/             # format check
make test          # runs pytest (handles venv internally)
make fmt           # black format
make lint          # ruff lint
make install-dev   # first-time setup
make rust-dev      # build Rust parser adapter (optional, requires maturin)

# Frontend (from frontend/ directory)
cd frontend && npm run lint        # ESLint
cd frontend && npm run typecheck   # tsc --noEmit
cd frontend && npm run test        # Jest
cd frontend && npm run test:e2e    # Playwright
```

## Quality Gates

Run before every commit: `ruff check` + `black --check` + `pytest`. Frontend: `lint` + `typecheck` + `test`.

## Architecture

Full-stack Rocket League replay analysis SaaS:

- **Pipeline**: Replay ingestion (CRC validation) -> Parser adapter (Rust pyo3 optional, null fallback) -> Normalize -> Event detection -> Analysis (14 modules) -> Report (JSON + Markdown)
- **Backend**: FastAPI + SQLAlchemy + Celery/Redis (`src/rlcoach/`)
- **Frontend**: Next.js 14 App Router + NextAuth + Tailwind (`frontend/`)
- **Infra**: PostgreSQL 16, Redis 7, Docker Compose for local dev

## Code Style

- Python: Black (88 cols), Ruff (E/W/F/I/B/C4/UP rules), snake_case
- TypeScript: strict mode, `@/*` path alias, 2-space indent
- Conventional commits: `type(scope): description`

## Key Conventions

- Analysis modules return `{"per_player": {...}, "per_team": {...}}` dicts
- Expensive analyzers are cached at aggregator level in `analysis/__init__.py`
- Tests mirror `src/` tree; use `tests/fixtures/builders.py` for synthetic data
- Large replay fixtures go through Git LFS in `assets/replays/`
- `PYTHONPATH=src` is required when running pytest directly

## Local Dev

```bash
docker compose up -d postgres redis   # start DB + cache
cp .env.example .env                  # configure environment
make install-dev                      # install Python deps
cd frontend && npm ci                 # install Node deps
```

## References

@AGENTS.md for detailed module docs, import conventions, and analysis patterns.
