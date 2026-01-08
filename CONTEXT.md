# Project Context — DO NOT DELETE

**Last Updated**: Phase 1 - SaaS Fixes (IN PROGRESS)

## Protocol Reminder (Re-read on every phase start)

**The Loop**: IMPLEMENT → TYPECHECK → LINT → BUILD → TEST → REVIEW → FIX → SLOP REMOVAL → COMMIT

**Quality gates:**
```bash
source .venv/bin/activate
PYTHONPATH=src pytest -q
ruff check src/
black --check src/
```

**If context feels stale:** Re-read `AUTONOMOUS_BUILD_CLAUDE.md` for the full protocol.

## Build Context

**Type**: Critical bug fixes for SaaS launch
**Plan location**: `SAAS_FIXES_PLAN.md`
**Source**: Codex code review (2026-01-06)

## Current Phase: Phase 1 - Fix DB Initialization

Fixing database initialization to work with DATABASE_URL in SaaS mode.

## Project Setup

- Framework: Next.js 14 + FastAPI + PostgreSQL
- Styling: Tailwind CSS (dark mode)
- State: React hooks + server state
- Database: PostgreSQL via SQLAlchemy
- Queue: Celery + Redis
- Testing: pytest (388 tests)

## Critical Issues Being Fixed

1. **DB init** - app.py ignores DATABASE_URL, tries local config
2. **Auth** - Users not created in Postgres on OAuth login
3. **Replay persistence** - Worker doesn't persist to Replay/PlayerGameStats
4. **Schema drift** - Endpoints reference non-existent columns
5. **Mock data** - Dashboard pages use hardcoded data

## Key Files

- `src/rlcoach/api/app.py` - FastAPI app, lifespan handler
- `src/rlcoach/api/auth.py` - JWT validation middleware
- `src/rlcoach/worker/tasks.py` - Celery tasks for replay processing
- `src/rlcoach/db/writer.py` - Database writer for analysis results
- `src/rlcoach/db/models.py` - SQLAlchemy models
- `frontend/src/lib/auth.ts` - NextAuth configuration

## Schema Notes

- `bcpm` = boost consumed per minute (NOT boost_per_minute)
- `time_supersonic_s` = supersonic time in seconds (NOT supersonic_pct)
- Win/loss stored as uppercase: "WIN", "LOSS", "DRAW"

## API Contracts

### POST /api/v1/users/bootstrap
Creates user on first login
```json
Request: { "provider": "discord", "providerId": "123", "email": "...", "name": "..." }
Response: { "id": "uuid", "subscriptionTier": "free" }
```

### GET /api/v1/replays
Returns user's replays
```json
Response: { "replays": [...], "total": 42, "page": 1 }
```

## Design Decisions

- DATABASE_URL takes precedence over config file
- SAAS_MODE=true excludes CLI routers
- Users created via bootstrap endpoint on first OAuth login
- Replay persistence uses existing db/writer.py

## 196 Test Replays Available

Located in `/replays/` directory for testing the full pipeline.
