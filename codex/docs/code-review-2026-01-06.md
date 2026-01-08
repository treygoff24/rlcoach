# RLCoach Code Review (2026-01-06)

## Scope and Inputs
- Plans reviewed: `IMPLEMENTATION_PLAN.md`, `UX_IMPLEMENTATION_PLAN.md`, `SPEC.md`
- Code reviewed: `src/rlcoach` (api, db, worker), `frontend/src`, `docker-compose*.yml`, `nginx/nginx.conf`, `migrations/`, `scripts/`
- Note: Tests were not executed for this review.

## Executive Summary
Phase 1 infrastructure is largely in place, but the SaaS flow is not end-to-end. Phase 2 schema work exists, yet runtime wiring (DB init, user creation, and replay persistence) is incomplete. Phase 3+ features are partially implemented, with several critical integration gaps that block authentication, uploads, and dashboard data. The UX plan shows partial progress (dashboard and upload improvements), but many pages still use mock data. There is also a strategic mismatch between `SPEC.md` (local tool) and the SaaS plan, which needs alignment.

## Plan Adherence Summary

### Implementation Plan
| Phase | Status | Evidence and Gaps |
| --- | --- | --- |
| Phase 1: Infrastructure | Mostly complete | Dockerfiles, compose files, nginx config, `.env.example`, backup/rotation scripts, CI/CD workflows exist. Missing env wiring for `SAAS_MODE`, `ENVIRONMENT`, and `BACKEND_URL`. |
| Phase 2: PostgreSQL | Partial | Models and Alembic migrations exist, but session management is sync (not async) and planned services (`session_detection.py`, `replay_ownership.py`) are missing. |
| Phase 3: Auth | Partial | NextAuth and OAuth providers exist (Discord/Google), but no Postgres adapter or account linking; backend JWT expectations are not met. |
| Phase 4: Upload/Processing | Partial | Upload endpoint + Celery worker exist, but parsed data is not written into Postgres. Sync preview not implemented. |
| Phase 5: Dashboard | Partial | Layout and dashboard home are present, but replays/sessions/compare/detail pages still mock data and backend endpoints are missing or mismatched. |
| Phase 6: Stripe | Partial | Billing endpoints and webhook exist, but routes and auth tokens are inconsistent with plan and frontend integration. |
| Phase 7: AI Coach | Partial | Chat endpoint and UI exist, no streaming SSE, and budget reset logic is incomplete. |
| Phase 8: Polish/Launch | Not done | No evidence of launch gating or full QA pass. |

### UX Implementation Plan
| Phase | Status | Evidence and Gaps |
| --- | --- | --- |
| Phase 1: Critical Fixes | Partial | Dashboard uses real API + empty state; upload toasts/backoff and free preview exist. Missing “Check Status” button and 30s guidance copy. |
| Phase 2: Error Handling | Partial | Error boundary exists in dashboard layout and error mapping exists. Coach error states and global error boundary incomplete. |
| Phase 3: Onboarding/Landing | Partial | Landing page improved, but no testimonials/FAQ/video and no onboarding tour. Skeleton component library not implemented. |
| Phase 4: Streaming Coach | Not done | No SSE endpoint or streaming UI. |
| Phase 5+: Later phases | Not done | Rank benchmarks, trending, cause-effect insights not implemented. |

## Findings (ordered by severity)

### Critical
- SaaS DB initialization depends on local config; if `~/.rlcoach/config.toml` is missing, `init_db` is never called and all `get_session` usage fails. See `src/rlcoach/api/app.py:46-64`.
- Authentication is not connected to Postgres. `frontend/src/lib/auth.ts:92-166` lacks a NextAuth adapter or user bootstrap, but `src/rlcoach/api/auth.py` requires a DB user record; all authenticated API calls will 401. The JWT callback uses OAuth provider access tokens for backend calls, which the backend cannot validate (`frontend/src/lib/auth.ts:114-136`).
- Replay processing does not persist analysis into Postgres. The worker only writes JSON and sets `UploadedReplay`/`UserReplay` without inserting `Replay` or `PlayerGameStats`, which leaves dashboards empty and can violate FK constraints (`src/rlcoach/worker/tasks.py:171-196`).
- Production safety gap: CLI routers (no auth) can be exposed if `SAAS_MODE`/`ENVIRONMENT` are not set. `docker-compose.prod.yml` does not set these envs (`docker-compose.prod.yml:38-51`), so `src/rlcoach/api/app.py:118-145` will include unauthenticated routes in production.
- Frontend server routes call the backend with OAuth access tokens and default localhost backend URL. Stripe and coach flows will fail in containers (`frontend/src/app/api/stripe/create-checkout/route.ts:5-22`, `frontend/src/app/api/stripe/create-portal/route.ts:5-22`, `frontend/src/app/api/coach/chat/route.ts:5-23`, `frontend/src/app/api/v1/[...path]/route.ts:18-53`, `docker-compose.prod.yml:91-107`).
- Benchmarks and GDPR endpoints reference columns that do not exist in `PlayerGameStats`. This will crash those endpoints (`src/rlcoach/api/routers/users.py:618-626`, `src/rlcoach/api/routers/gdpr.py:123-140`, `src/rlcoach/db/models.py:102-183`).

### High
- Frontend-backend contract mismatch for replays and replay details. The frontend expects `result` and `score`, but the API payload omits them (`frontend/src/app/(dashboard)/replays/page.tsx:7-26`, `frontend/src/app/(dashboard)/replays/[id]/page.tsx:20-71`, `src/rlcoach/api/routers/replays.py:89-125`).
- Trends page targets `/api/v1/analysis/trends`, but the analysis router is not prefixed with `/api/v1` and is only mounted in non-SaaS mode (`frontend/src/app/(dashboard)/trends/page.tsx:84-92`, `src/rlcoach/api/routers/analysis.py:18-38`, `src/rlcoach/api/app.py:133-145`).
- Route conflict and auth guard mismatch: both `frontend/src/app/page.tsx` and `frontend/src/app/(dashboard)/page.tsx` map to `/`, while middleware protects `/dashboard` only (`frontend/src/middleware.ts:13-19`). This risks build conflicts or an unprotected dashboard home.
- Upload size limits are inconsistent across layers: backend allows 50MB (`src/rlcoach/api/routers/replays.py:28-30`), nginx caps at 10MB (`nginx/nginx.conf:106-148`), and frontend copy assumes 10MB (`frontend/src/lib/errors.ts:26-34`).
- Upload endpoint uses `UploadFile.size`, which FastAPI does not supply; this can raise `AttributeError` and block uploads (`src/rlcoach/api/routers/replays.py:171-173`).
- Win-rate calculations assume lowercase results while the writer stores uppercase values (`src/rlcoach/api/routers/users.py:413-466`, `src/rlcoach/db/writer.py:137-142`).

### Medium
- Many dashboard pages still use mock data and have no API wiring: replays list, replay detail, compare, sessions (`frontend/src/app/(dashboard)/replays/page.tsx:20-41`, `frontend/src/app/(dashboard)/replays/[id]/page.tsx:20-71`, `frontend/src/app/(dashboard)/compare/page.tsx:8-31`, `frontend/src/app/(dashboard)/sessions/page.tsx:18-41`).
- Client pages depend on `session.accessToken` for data fetching even though `/api/v1` proxy already attaches JWT; sessions without provider access tokens will never fetch data (`frontend/src/app/(dashboard)/page.tsx:268-311`, `frontend/src/app/(dashboard)/trends/page.tsx:74-113`).
- Celery beat tasks are configured but there is no beat service in compose, so scheduled deletions will not run (`src/rlcoach/worker/celery_app.py:33-57`).
- GDPR removal processing is unauthenticated and stored in-memory only; requests will be lost on restart and could be abused (`src/rlcoach/api/routers/gdpr.py:90-208`).
- Coach endpoint uses synchronous Anthropic client inside an async FastAPI handler; under load this can block the event loop (`src/rlcoach/api/routers/coach.py:650-720`).
- Billing endpoints are mounted at `/billing` while plan expects `/api/v1/billing`, and frontend mixes proxy vs direct backend calls (`src/rlcoach/api/routers/billing.py:28-54`).

### Low
- Partial index uses `Column("is_me")` instead of the model column; may behave unexpectedly on `create_all` (`src/rlcoach/db/models.py:185-193`).
- Rate limiter fails open if Redis is down; this is an availability tradeoff but should be explicit in risk docs (`src/rlcoach/api/rate_limit.py:14-33`).
- `deploy.replicas` is ignored by docker-compose in non-swarm mode (`docker-compose.prod.yml:86-87`).

## Business Use Case Fit
The core SaaS loop (sign-in -> upload -> processing -> dashboard -> coach/billing) is currently blocked by missing user persistence, DB initialization in SaaS mode, and replay persistence into Postgres. Even if auth succeeds, most dashboard pages are still mock-based. Additionally, `SPEC.md` describes a local, non-commercial tool, while the codebase is pursuing SaaS. This mismatch makes it hard to validate whether the business use case is being met; it should be resolved explicitly.

## Code Quality Observations
- Strengths: solid sanitation for uploads and coach content, clear modularization for analysis and worker tasks, and good use of Pydantic models.
- Gaps: mixing local CLI config with SaaS runtime, inconsistent API route prefixes, and incomplete wiring between Next.js and FastAPI. Several endpoints reference columns that do not exist, indicating a schema drift risk.

## Tests and Verification
- Tests exist for parsing and analysis modules, but there are no tests for SaaS endpoints, auth flows, upload pipeline, Stripe, or Next.js API proxy. Frontend pages with mock data have no API integration tests.

## Proactive Recommendations (prioritized)
1. Wire NextAuth to Postgres (adapter or backend bootstrap) so users are created and sessions map to `users`/`accounts`; remove OAuth access tokens as backend auth.
2. Initialize DB on startup whenever `DATABASE_URL` is set, regardless of local config. Set `SAAS_MODE=true`, `ENVIRONMENT=production`, and `BACKEND_URL=http://backend:8000` in compose.
3. Update the worker to persist replay analysis into `Replay` and `PlayerGameStats` using `db/writer.py` or a SaaS-specific pipeline, then create `UserReplay` after `Replay` exists.
4. Align API routes and contracts: standardize `/api/v1` prefixes, ensure backend responses match frontend expectations, and remove mock data from replays/compare/sessions/detail.
5. Fix schema mismatches (benchmarks and GDPR fields) and unify win/loss casing across DB and API.
6. Implement missing UX plan items (global error boundary, onboarding tour, landing testimonials/FAQ/video, streaming coach, skeleton components).
7. Add tests for SaaS API endpoints and worker pipeline; add basic e2e smoke tests for sign-in, upload, dashboard, coach, and billing.

## Notes
- Tests were not executed during this review.
