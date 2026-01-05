# rlcoach Context — SaaS Build

**Last Updated**: 2026-01-05
**Current Phase**: Post-Launch UX Polish (Complete)

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
| 6 | Stripe Payments & Subscription | **COMPLETE** |
| 7 | AI Coach | **COMPLETE** |
| 8 | Polish, Testing & Launch | **COMPLETE** |

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

## Phase 6 Deliverables (Complete)

Backend billing API:
- `src/rlcoach/api/routers/billing.py` - Stripe checkout, portal, status endpoints
- POST /billing/checkout - Create Stripe Checkout session
- POST /billing/portal - Create customer billing portal session
- GET /billing/status - Get subscription status
- POST /stripe/webhook - Handle Stripe webhook events

Webhook handlers:
- checkout.session.completed - Activate Pro subscription
- customer.subscription.updated - Sync subscription status
- customer.subscription.deleted - Downgrade to free tier
- invoice.payment_failed - Mark subscription past_due

Frontend routes:
- /api/stripe/create-checkout - Proxy to backend
- /api/stripe/create-portal - Proxy to backend
- /api/stripe/webhook - Forward webhooks

## Phase 7 Deliverables (Complete)

AI Coach services:
- `src/rlcoach/services/coach/` - Coach service module
- `prompts.py` - System prompt with RL coaching expertise
- `tools.py` - Data access tools (get_recent_games, get_stats_by_mode, etc.)
- `budget.py` - Token budget management (150K/month)

Coach tools:
- get_recent_games - Fetch player's recent matches
- get_stats_by_mode - Aggregate stats by playlist
- get_game_details - Deep dive into a specific replay
- get_rank_benchmarks - Compare to rank averages
- save_coaching_note - Persist coaching observations

Frontend integration:
- Updated coach page to call real API
- Session continuity across messages
- Token budget display
- Error handling

## Phase 8 Deliverables (Complete)

Code quality:
- Applied auto-lint fixes (ruff --fix)
- All 394 backend tests passing
- Frontend builds successfully

Verification:
- All API endpoints implemented
- Frontend pages render correctly
- Auth flow complete (OAuth via Discord/Google)
- Stripe payment flow wired up
- AI Coach with tools and extended thinking

## Build Complete

**All 8 phases completed successfully.**

The rlcoach SaaS product is ready for deployment. Key components:
- Next.js frontend with 7 dashboard pages
- FastAPI backend with replay processing
- PostgreSQL database with all models
- Stripe payments for Pro subscription ($10/mo)
- AI Coach powered by Claude Opus 4.5
- Docker Compose for local development
- CI/CD pipelines configured

To deploy:
1. Configure environment variables from `.env.example`
2. Set up Stripe products/prices
3. Configure OAuth providers (Discord, Google)
4. Run `docker compose -f docker-compose.prod.yml up`

---

## UX Polish Sprint (2026-01-05)

After initial build, completed 8-phase UX polish pass:

### Phase 1-2: Critical Fixes
- Dashboard fetches real API data (`/api/v1/users/me/dashboard`)
- Free tier users get 1 complimentary AI coach message
- Upload polling with exponential backoff (2s → 30s)
- Retry button for failed uploads

### Phase 3: Landing Page Redesign
- Fixed header with blur effect
- Hero with animated gradient orbs
- Stats banner, How It Works, 6 feature cards
- AI Coach spotlight, FAQ accordion
- Conversion-focused CTAs

### Phase 4-5: Toast & Error Handling
- Toast notification system (success/error/warning/info)
- ErrorBoundary component wrapping dashboard
- Centralized error parsing utilities

### Phase 6: Rank Benchmarks
- Dashboard stat cards show Above/Below/On-par badges
- Parallel fetch for benchmarks vs user's rank tier
- `/api/v1/users/me/benchmarks` endpoint

### Phase 7: Real Trends Data
- Trends API with optional auth for user scoping
- UserReplay join for multi-tenant data isolation
- Frontend fetches real data with loading/error states

### Phase 8: Enhanced Insights
- Priority ranking (CRITICAL/HIGH/MEDIUM/LOW/INFO)
- Contributing factors array for cause-effect
- Actionable recommendations on every insight
- Session recap endpoint (`/sessions/{id}/recap`)

### Security Fixes (Codex Review)
- Trends API: Period validation with explicit allowlist
- Trends API: Unauthenticated requests return empty (prevents data leakage)
- Benchmarks: Rate limiting (30 req/min)

**Quality:** 388 tests passing, lint clean
