# Full App Review Report (2026-01-08)

## Problems / Bugs / Errors / Inefficiencies
- Critical: Rust frame parsing filters actors to `kind.is_car` and yields empty `players`, so per-frame analysis collapses to zeros. `parsers/rlreplay_rust/src/lib.rs:728`
- Critical: Docker builds fail because `setup.py` is copied but does not exist. `backend/Dockerfile:18`, `worker/Dockerfile:18`
- Critical: Uploads are saved to `/tmp/rlcoach/uploads` in the backend container but not shared with the worker, so processing fails with "file not found." `src/rlcoach/api/routers/replays.py:250`, `src/rlcoach/worker/tasks.py:150`, `docker-compose.yml:46`
- Major: Coach chat and Stripe server routes send `session.accessToken`, but NextAuth never sets it, so these routes 401. `frontend/src/lib/auth.ts:116`, `frontend/src/app/api/coach/chat/route.ts:18`, `frontend/src/app/api/stripe/create-checkout/route.ts:16`, `frontend/src/app/api/stripe/create-portal/route.ts:16`
- Major: GDPR endpoints reference non-existent fields (`steam_id`, `epic_id`, `display_name`) on `PlayerGameStats`, so they error out. `src/rlcoach/api/routers/gdpr.py:123`
- Major: Dev `docker-compose` does not set `BACKEND_URL`, so Next server routes and NextAuth bootstrap default to localhost inside the container and cannot reach the backend. `docker-compose.yml:85`, `frontend/src/app/api/v1/[...path]/route.ts:18`

### Additional Problems / Inefficiencies
- Major: Worker creates `UserReplay` even after `write_report_saas` fails (non-`ReplayExistsError`), risking FK violations and masking persistence failures. `src/rlcoach/worker/tasks.py:185`
- Major: SQLAlchemy partial index uses a new `Column("is_me")`, which can break `Base.metadata.create_all` in SQLite/local dev. `src/rlcoach/db/models.py:190`
- Medium: `/coach` is blocked for non-Pro users in middleware, so the free preview flow is unreachable despite backend support. `frontend/src/middleware.ts:12`
- Medium: Boost metric naming is inconsistent (`bpm` is amount/min, `bcpm` is pads/min) but DB stores `bpm` as BCPM, so stored stats are likely wrong. `src/rlcoach/analysis/boost.py:308`, `src/rlcoach/db/writer.py:347`
- Medium: Coach tool mode uses playlist strings ("Ranked Doubles") that do not match stored enums, so mode filtering returns empty data. `src/rlcoach/services/coach/tools.py:133`
- Efficiency: Async routes call blocking Stripe/Anthropic SDKs and sync SQLAlchemy, which can stall the event loop under load. `src/rlcoach/api/routers/billing.py:74`, `src/rlcoach/api/routers/coach.py:695`

### Minor Consistency Issues
- Passing threshold doc says 200 UU but constant is 80 UU; metrics may be out of spec. `src/rlcoach/analysis/passing.py:17`
- Kickoff `goals_for/goals_against` is never attributed (placeholder `pass`). `src/rlcoach/analysis/kickoffs.py:148`
- Make targets do not activate `.venv`, so `make test/lint/fmt` fails unless users manually activate. `Makefile:15`
- `NEXT_PUBLIC_API_URL` is set in compose but never used in the frontend codepath. `docker-compose.yml:88`

## Improvements / Missing / Redo
- Persist GDPR requests and protect processing with admin auth; in-memory `_removal_requests` is wiped on restart. `src/rlcoach/api/routers/gdpr.py:90`
- Account deletion should also remove OAuth accounts/sessions and user-replay links to avoid re-login to anonymized users. `src/rlcoach/api/routers/users.py:480`
- Align Alembic migrations with models (missing indexes and on-delete cascade). `migrations/versions/20260103_001_initial_schema.py:125`
- Use replay header timestamp for `metadata.started_at_utc`; it is currently "time of processing," which skews session grouping. `src/rlcoach/report.py:210`
- Stream uploads (hash while streaming) and store in shared/object storage to avoid memory spikes and duplicate parsing work. `src/rlcoach/api/routers/replays.py:200`
- Add tests for SaaS endpoints, worker pipeline, and Next API proxy/auth; current tests focus on local CLI routers.

## Questions / Assumptions
- Is the free-preview coach meant to be available to non-Pro users (backend allows it, middleware blocks it)?
- Are playlist values intended to be uppercase enums (`DOUBLES`) or human strings (`Ranked Doubles`) for all tools?
- Is the Vite `gui` intended to remain alongside the Next.js app, or should one be deprecated?

## Tests Not Run
- Not run (static review only).
