# rlcoach Context — SaaS Build

**Last Updated**: 2026-01-03
**Current Phase**: Phase 2 (Database & Migration)

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
| 2 | PostgreSQL Database & Migration | **READY TO START** |
| 3 | Authentication & Authorization | Pending |
| 4 | Replay Upload & Processing | Pending |
| 5 | Dashboard Frontend | Pending |
| 6 | Stripe Payments & Subscription | Pending |
| 7 | AI Coach | Pending |
| 8 | Polish, Testing & Launch | Pending |

**Critical Path**: Infrastructure -> Database -> Auth -> Upload -> Dashboard -> AI Coach

Phase 6 (Payments) can run parallel to Phase 5 after Phase 3 completes.

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

## Codex Checkpoints

- [x] After drafting spec — Approved
- [x] After drafting implementation plan — Approved
- [ ] After completing Phase 1 — **PENDING REVIEW**
- [ ] After completing Phase 2
- [ ] ...after each phase...
- [ ] Before declaring build complete

## Next Action

**Begin Phase 2: PostgreSQL Database & Migration**
1. Design PostgreSQL schema (User, OAuthAccount, CoachSession, etc.)
2. Set up Alembic migrations
3. Update database session for PostgreSQL + async
4. Migrate existing SQLite models
5. Add UserReplay and session detection logic

See `IMPLEMENTATION_PLAN.md` Phase 2 for full task list.
