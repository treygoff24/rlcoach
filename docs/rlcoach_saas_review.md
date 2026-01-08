# RLCoach SaaS Review

## Findings

### Critical
- Auth and user provisioning are not aligned: NextAuth is configured as JWT-only and does not persist users, while the FastAPI auth layer requires a `users` table entry to exist, so authenticated API calls will 401 even after a successful OAuth login. Evidence: `frontend/src/lib/auth.ts:92`, `src/rlcoach/api/auth.py:151`.
- Server-side Next routes for coach and billing forward OAuth provider access tokens as Bearer auth, but the backend expects a NextAuth-signed JWT; this breaks AI coach chat and Stripe checkout/portal flows. Evidence: `frontend/src/app/api/coach/chat/route.ts:18`, `frontend/src/app/api/stripe/create-checkout/route.ts:16`, `frontend/src/app/api/stripe/create-portal/route.ts:16`, `src/rlcoach/api/auth.py:130`.
- The replay processing worker only writes parsed JSON to disk and updates `UploadedReplay`, but never inserts `Replay`, `PlayerGameStats`, or `Player` data; dashboards and analytics will be empty and the `UserReplay` insert can violate the foreign key because the `replays` row does not exist. Evidence: `src/rlcoach/worker/tasks.py:171`, `src/rlcoach/worker/tasks.py:186`, `src/rlcoach/db/models.py:479`.
- The Next.js routing tree has two root pages (`/`): the marketing page and the dashboard page are both `page.tsx` in different route groups, which is an invalid or ambiguous route setup and will fail build or route resolution. Evidence: `frontend/src/app/page.tsx:1`, `frontend/src/app/(dashboard)/page.tsx:1`.
- `/api/v1/users/me/benchmarks` references non-existent columns (`boost_per_minute`, `supersonic_pct`) on `PlayerGameStats`, so the dashboard benchmark card should error at runtime. Evidence: `src/rlcoach/api/routers/users.py:625`, `src/rlcoach/api/routers/users.py:626`, `src/rlcoach/db/models.py:125`.

### High
- Trends calls `/api/v1/analysis/trends`, but the analysis router is disabled in SaaS mode, so the Trends page will 404 in production. Evidence: `src/rlcoach/api/app.py:133`, `frontend/src/app/(dashboard)/trends/page.tsx:85`.
- Core dashboard pages are still fed by mock data and do not call any API, so users will see fake replays/sessions/compare/detail data after upload. Evidence: `frontend/src/app/(dashboard)/replays/page.tsx:20`, `frontend/src/app/(dashboard)/sessions/page.tsx:18`, `frontend/src/app/(dashboard)/compare/page.tsx:8`, `frontend/src/app/(dashboard)/replays/[id]/page.tsx:20`.
- Session cards link to `/sessions/{id}` but there is no route implementation, so these links will 404. Evidence: `frontend/src/app/(dashboard)/sessions/page.tsx:65`.
- Subscription tier refresh uses the OAuth provider access token to call the backend, so tier updates will fail and the UI will keep users stuck on free. Evidence: `frontend/src/lib/auth.ts:122`, `frontend/src/lib/auth.ts:130`.
- Win/loss comparisons use lowercase strings in multiple places, while the replay writer uses uppercase, so win-rate and pattern calculations will be wrong or zero. Evidence: `src/rlcoach/api/routers/users.py:413`, `src/rlcoach/services/coach/tools.py:168`, `src/rlcoach/db/writer.py:137`.
- Auth middleware protects `/replays` and `/coach` but not `/sessions`, `/compare`, or `/trends`, and tests expect those pages to require auth. Evidence: `frontend/src/middleware.ts:13`, `frontend/e2e/dashboard.spec.ts:62`.

### Medium
- GDPR removal requests query non-existent `PlayerGameStats` columns and store requests only in memory, which will lose submissions on restart and likely 500 on lookup. Evidence: `src/rlcoach/api/routers/gdpr.py:90`, `src/rlcoach/api/routers/gdpr.py:123`, `src/rlcoach/db/models.py:102`.
- Terms and Privacy pages are explicit templates and not production-ready legal documents, which is a launch blocker if this goes public. Evidence: `frontend/src/app/terms/page.tsx:5`, `frontend/src/app/privacy/page.tsx:5`.
- Marketing and docs are misaligned with the current product intent: the spec says local-only and not for sale, while deployment/docs/marketing describe a paid SaaS with Stripe and cloud hosting. Evidence: `SPEC.md:14`, `docs/deployment.md:3`, `frontend/src/app/page.tsx:240`.
- Token budget numbers conflict between product copy and backend limits, which will create trust issues when a user hits the quota. Evidence: `docs/user-guide.md:96`, `src/rlcoach/services/coach/budget.py:12`.
- The AI Coach tool benchmarks are explicitly placeholder estimates and not based on real aggregate data, which undermines product credibility if surfaced. Evidence: `src/rlcoach/services/coach/tools.py:236`.
- UI copy and error messaging reference a 10MB upload limit, but the backend accepts 50MB, so users will be confused by mismatched limits. Evidence: `frontend/src/lib/errors.ts:38`, `docs/user-guide.md:142`, `src/rlcoach/api/routers/replays.py:29`.

### Low
- Several UI pages are monolithic and should be broken into components for maintainability (landing page, dashboard, replay detail). Evidence: `frontend/src/app/page.tsx:1`, `frontend/src/app/(dashboard)/page.tsx:1`, `frontend/src/app/(dashboard)/replays/[id]/page.tsx:1`.
- The repo includes multiple frontends (`frontend` Next.js and `gui` Vite template). This increases maintenance cost and makes it unclear which UI is canonical. Evidence: `gui/README.md:1`.

## UX and Delight Notes
- Visual direction is strong and cohesive. The neon, motion, and typography match a high-energy, gamer-focused vibe that should resonate with Rocket League players (`frontend/src/app/globals.css:1`).
- The marketing page feels premium but leans heavily on unverified social proof ("50K+", "2.5K+", "98% accuracy"), which can erode trust if not true (`frontend/src/app/page.tsx:67`).
- The in-app experience lacks an onboarding loop after login: users are not guided to find replay files, upload, and see their first insight. The empty state on dashboard helps, but there is no visible "first replay" checklist across the other views.
- Coach UX shows a paywall but does not let users select a replay or add context, so the "AI coach understands your game" promise is not met (`frontend/src/app/(dashboard)/coach/page.tsx:66`).

## Product and Business Criteria
- The product direction is split between a local-only CLI tool and a paid SaaS. This creates conflicting requirements for privacy, onboarding, pricing, and deployment. A decision is needed on the core product model to avoid wasted work (`SPEC.md:14`, `docs/deployment.md:3`).
- The pipeline still documents a critical parser limitation where player frames are missing, which means many analytics are zero and the core coaching value is not delivered (`project-overview.md:156`).
- Pricing at $10/month may not cover Opus 4.5 + extended thinking usage unless you enforce strict message limits or reduce token budgets. The current copy promises "unlimited" coaching in Pro (`frontend/src/app/page.tsx:270`).

## Testing and Quality Gaps
- Frontend E2E tests skip authentication-dependent flows and have placeholder tests, so there is little coverage of the most important paths (upload -> processing -> dashboard -> coach). Evidence: `frontend/e2e/upload.spec.ts:11`, `frontend/e2e/coach.spec.ts:48`.
- There are no visible backend tests for the SaaS API routers (users, replays, billing, coach). This increases regression risk for production endpoints.

## Open Questions and Assumptions
- Is the target product a paid SaaS, a local-only tool, or both? The current docs and code are pulling in opposite directions.
- Do you want NextAuth to persist users in Postgres (via `@auth/pg-adapter`), or should the backend accept stateless users without a DB row?
- Where should replay analysis results live for SaaS: in Postgres (for queries) or JSON storage only (for audit)?
- How do you want to handle replay ownership and dedupe when multiple users upload the same file?
- Is the AI Coach intended to be replay-aware by default, or only on-demand when a replay is selected?
