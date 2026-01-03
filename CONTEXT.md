# rlcoach Context — SaaS Build

**Last Updated**: 2026-01-03
**Current Phase**: Phase 6 (Stripe Payments & Subscription)

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
| 3 | Authentication & Authorization | **COMPLETE** |
| 4 | Replay Upload & Processing | **COMPLETE** |
| 5 | Dashboard Frontend | **COMPLETE** |
| 6 | Stripe Payments & Subscription | **IN PROGRESS** |
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

## Phase 3 Deliverables (Complete)

Frontend auth:
- `frontend/src/lib/auth.ts` - NextAuth v5 configuration
- `frontend/src/middleware.ts` - Route protection middleware
- `frontend/src/app/api/auth/[...nextauth]/route.ts` - Auth API handlers
- `frontend/src/app/login/page.tsx` - OAuth login page (Discord, Google)
- `frontend/src/app/upgrade/page.tsx` - Pro subscription upgrade page

OAuth providers:
- Discord (primary - RL community)
- Google (convenience fallback)
- Steam (placeholder, disabled until OpenID implementation)

Backend auth:
- `src/rlcoach/api/auth.py` - JWT middleware with PyJWT
- Token validation and user extraction
- `AuthenticatedUser`, `OptionalUser`, `ProUser` dependencies

Protected API endpoints:
- `src/rlcoach/api/routers/users.py` - User profile, subscription info
- `src/rlcoach/api/routers/replays.py` - Replay upload, list, delete
- `src/rlcoach/api/routers/coach.py` - AI coach (Pro tier only)

Subscription tier checks:
- JWT includes subscriptionTier claim
- Middleware checks Pro tier for /coach routes
- FastAPI `require_pro` dependency for coach endpoints

## Phase 4 Deliverables (Complete)

Upload API:
- `src/rlcoach/api/routers/replays.py` - Upload, list, delete, library endpoints
- SHA256 deduplication to avoid re-processing identical files
- Queue backpressure check rejects uploads when system overloaded

Background worker:
- `src/rlcoach/worker/tasks.py` - Celery tasks for replay processing
- `process_replay` task with database status updates
- `migrate_to_cold_storage` task for Backblaze B2 archival
- `cleanup_temp_files` and `check_disk_usage` maintenance tasks
- Subprocess with 30s timeout and 512MB memory limit

Frontend upload:
- `frontend/src/components/UploadDropzone.tsx` - Drag-drop with progress
- Multiple file upload support
- Status polling for processing updates

## Phase 5 Deliverables (Complete)

Dashboard layout:
- `frontend/src/components/layout/Sidebar.tsx` - Navigation sidebar
- `frontend/src/components/layout/Navbar.tsx` - Top navbar with mobile menu
- `frontend/src/components/layout/UploadModal.tsx` - Modal wrapper for upload
- `frontend/src/app/(dashboard)/layout.tsx` - Dashboard layout wrapper

Dashboard pages (all 7):
- `page.tsx` - Home: Topline stats, mechanics breakdown, quick actions
- `replays/page.tsx` - Replay list with filters and pagination
- `replays/[id]/page.tsx` - Replay detail with 7 tabs (Overview, Mechanics, Boost, Positioning, Timeline, Defense, Offense)
- `sessions/page.tsx` - Sessions grouped by play session
- `trends/page.tsx` - Performance trends with time-series charts
- `compare/page.tsx` - Comparison vs Rank and vs Self modes
- `coach/page.tsx` - AI coach chat interface (Pro tier gated)
- `settings/page.tsx` - Profile, subscription, linked accounts, preferences

Fixes applied:
- Downgraded ESLint 9→8 for eslint-config-next compatibility
- Simplified globals.css (removed shadcn CSS variables)
- Fixed gitignore to allow frontend/replays directory

## Next Action

**Phase 6: Stripe Payments & Subscription**
1. Create Stripe products/prices (Pro tier $10/mo)
2. Implement checkout session API endpoint
3. Add webhook handler for subscription events
4. Connect upgrade flow to Stripe
5. Store subscription status in user model

See `IMPLEMENTATION_PLAN.md` Phase 6 for full task list.
