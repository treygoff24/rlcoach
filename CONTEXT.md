# rlcoach Context — SaaS Build

**Last Updated**: 2026-01-03
**Current Phase**: Phase 3 (Authentication & Authorization)

## Protocol Reminder

Follow `AUTONOMOUS_BUILD_CLAUDE.md`:
1. Call Codex at checkpoints (after spec, after plan, after each phase, when stuck)
2. Update CONTEXT.md after each phase
3. Commit often with descriptive messages
4. No blocking on user input during build

**Quality gates:**
```bash
source .venv/bin/activate
PYTHONPATH=src pytest -q
ruff check src/
black --check src/
```

## Build Context

**Type**: Full product build (CLI -> SaaS)
**Spec location**: `docs/plans/2026-01-03-rlcoach-saas-design.md`
**Plan location**: `IMPLEMENTATION_PLAN.md`

## What We're Building

**rlcoach SaaS** — Subscription-based Rocket League coaching platform:
- Free tier: Unlimited replay uploads, full dashboard (7 pages, 7 tabs)
- Pro tier ($10/mo): AI coach powered by Claude Opus 4.5 with extended thinking

**Tech Stack**: Next.js + FastAPI + PostgreSQL + Stripe + Cloudflare on Hetzner

## Implementation Phases

| Phase | Name | Status |
|-------|------|--------|
| 1 | Infrastructure Foundation | **COMPLETE** |
| 2 | PostgreSQL Database & Migration | **COMPLETE** |
| 3 | Authentication & Authorization | **READY TO START** |
| 4 | Replay Upload & Processing | Pending |
| 5 | Dashboard Frontend | Pending |
| 6 | Stripe Payments & Subscription | Pending |
| 7 | AI Coach | Pending |
| 8 | Polish, Testing & Launch | Pending |

**Critical Path**: Infrastructure -> Database -> Auth -> Upload -> Dashboard -> AI Coach

## Phase 1 Deliverables (Complete)

Infrastructure files created:
- `docker-compose.yml` - Development orchestration
- `docker-compose.prod.yml` - Production orchestration
- `backend/Dockerfile` - FastAPI container (multi-stage)
- `worker/Dockerfile` - Celery worker container
- `frontend/Dockerfile` - Next.js container (multi-stage)
- `nginx/Dockerfile` + `nginx.conf` - Reverse proxy with rate limiting
- `.env.example` - All required secrets documented
- `.github/workflows/ci.yml` - CI pipeline (tests, lint, build)
- `.github/workflows/deploy.yml` - CD pipeline (build, push, deploy)
- `scripts/backup.sh` - PostgreSQL backup to Backblaze B2
- `scripts/restore.sh` - Database restore from backup
- `scripts/rotate-secrets.sh` - Secret rotation helper
- `alembic.ini` + `migrations/env.py` - Database migration setup

Frontend skeleton:
- `frontend/package.json` - Next.js 14 with dependencies
- `frontend/src/app/` - App router with landing page
- `frontend/tailwind.config.ts` - Dark theme with RL-inspired colors

Worker module:
- `src/rlcoach/worker/` - Celery tasks for replay processing
- Enhanced health endpoint with Redis check

## Phase 2 Deliverables (Complete)

Database models added:
- `User` - Account with subscription fields (tier, stripe IDs, token budget)
- `OAuthAccount` - NextAuth accounts table for OAuth providers
- `Session` - NextAuth session storage
- `VerificationToken` - Email verification
- `CoachSession` - AI coach conversation tracking
- `CoachMessage` - Individual messages with token counts
- `CoachNote` - Persistent coaching notes (user + AI)
- `UploadedReplay` - Upload tracking with status
- `UserReplay` - Many-to-many replay ownership

Session management:
- Updated `session.py` to support both SQLite and PostgreSQL
- `DATABASE_URL` env var controls backend
- Connection pooling for PostgreSQL

Replay sessions:
- `replay_sessions.py` - Session detection and grouping
- 30-minute gap default for session boundaries
- Deterministic session ID generation

Migration:
- `migrations/versions/20260103_001_initial_schema.py`
- Full schema with all tables and indexes
- PostgreSQL partial index for is_me optimization

## Next Action

**Begin Phase 3: Authentication & Authorization**
1. Create NextAuth configuration for Next.js
2. Implement Discord, Steam, Google OAuth providers
3. Create FastAPI JWT middleware
4. Add auth-required endpoints
5. Implement subscription tier checks

See `IMPLEMENTATION_PLAN.md` Phase 3 for full task list.
