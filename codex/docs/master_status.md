# RLCoach Master Status (Single Source of Truth)

**Last updated:** 2026-02-10
**Purpose:** Provide a durable, detailed snapshot of current state, plan status, gaps, and blockers for all future sessions.

---

## 1) Executive Summary

- **Core local pipeline is implemented** (ingest → parse/normalize → events → analysis → JSON + Markdown report), with a pluggable Rust adapter and comprehensive pytest coverage.
- **SaaS product is partially implemented**: backend + frontend exist, OAuth login + upload + dashboard + coach flows are wired, and Stripe endpoints are present, but formal E2E verification and several plan phases remain uncompleted or stale in docs.
- **Critical blocker (historical):** Rust adapter network frames previously emitted empty players arrays; current code now produces per-frame car telemetry for at least `testing_replay.replay`, but mapping robustness still needs hardening (see parser gap section).
- **Plan docs are stale:** `IMPLEMENTATION_PLAN.md` and `UX_IMPLEMENTATION_PLAN.md` checklists do not reflect actual code state. `SAAS_FIXES_PLAN.md` is closest to current reality but Phase 6 remains unchecked.
- **Ballchasing parity is no longer a target:** parity tests, scripts, fixtures, and helpers have been removed to avoid enforcing external alignment.
- **Parity artifacts archived:** legacy parity plans/sprints moved to `codex/archive/ballchasing-parity/`.
- **Parser reliability gate (2026-02-10):** corpus harness on 202 local replays reported `header_success_rate=1.0`, `network_success_rate=0.9950495`, and `degraded_count=1` (`boxcars_network_error` on one tournament replay). This meets the global `>=99.5%` target.
- **Backend decision gate (2026-02-10):** current outcome is **No-Go for non-boxcars backend implementation**. Criteria were: Go only if network success `<99.5%` or any ranked-standard class `>1%` degraded. Current ranked-standard bucket (`inferred_3`) is `0/65` degraded.

### 1.1 Parser Reliability Snapshot (2026-02-10)

- Diagnostics-first behavior is active: `parse_network()` returns explicit `NetworkDiagnostics` (`ok|degraded|unavailable`) instead of silent loss.
- Corpus metadata coverage from harness:
  - playlist buckets: inferred_2=108, inferred_3=65, tournament=20, inferred_4=6, private=2, inferred_1=1
  - match type buckets: 2v2=116, 3v3=78, 4v4=6, 1v1=2
  - engine build buckets: 251202.62834.504897=196, 250811.43331.492665=5, 250909.54128.495700=1
- Open reliability issue is isolated to one tournament replay (`replays/A181B28546BBD8AC71E63793B65BABAE.replay`), not ranked-standard.

---

## 2) Canonical Plans & Specs (Where to Look)

- **Primary local pipeline plan:** `codex/Plans/rlcoach_implementation_plan.md`
- **SaaS build plan:** `IMPLEMENTATION_PLAN.md`
- **Critical SaaS fixes:** `SAAS_FIXES_PLAN.md`
- **UX polish plan:** `UX_IMPLEMENTATION_PLAN.md`
- **Advanced mechanics plan:** `MECHANICS_IMPLEMENTATION_PLAN_v2.md`
- **SaaS spec:** `docs/plans/2026-01-03-rlcoach-saas-design.md`
- **UX spec:** `docs/plans/2026-01-04-ux-polish-spec.md`

---

## 3) Current Architecture (Implemented)

### 3.1 Core Local Pipeline (Working)

**Flow:** `ingest → parser adapter → normalize → events → analysis → report`.

- **Ingest & validation:** `src/rlcoach/ingest.py`
  - Handles size bounds, hashing, and CRC scaffolding.
  - CRC is still flagged as stubbed in report quality metadata.
- **Parser layer (pluggable):** `src/rlcoach/parser/`
  - `null_adapter.py` (header-only fallback)
  - `rust_adapter.py` (boxcars-backed pyo3 module)
  - `types.py` defines canonical dataclasses for Frame, PlayerFrame, BallFrame, BoostPadEventFrame, etc.
- **Normalization:** `src/rlcoach/normalize.py`
  - Builds `Frame` objects, aligns timestamps, maps players to canonical identities.
- **Events detection:** `src/rlcoach/events/`
  - Goals, demos, touches, boost pickups, kickoffs, challenges, timeline.
- **Analysis modules (14):** `src/rlcoach/analysis/`
  - fundamentals, boost, movement, positioning, passing, challenges, kickoffs, heatmaps, insights, mechanics, recovery, defense, xg, ball_prediction.
- **Reports:**
  - JSON: `src/rlcoach/report.py` (schema-conformant output)
  - Markdown: `src/rlcoach/report_markdown.py` with goldens under `tests/goldens/`.
- **CLI:** `src/rlcoach/cli.py` and entrypoints via `pyproject.toml`.
- **Offline viewer:** `src/rlcoach/ui.py`.

### 3.2 SaaS Backend (Working, partial)

**FastAPI app:** `src/rlcoach/api/app.py`
- Environment handling: `SAAS_MODE`, `ENVIRONMENT`, `DATABASE_URL`, etc.
- Routers:
  - Users: `src/rlcoach/api/routers/users.py`
  - Replays: `src/rlcoach/api/routers/replays.py`
  - Dashboard: `src/rlcoach/api/routers/dashboard.py`
  - Trends/compare: `users.py` (SaaS-safe endpoints)
  - Coach: `src/rlcoach/api/routers/coach.py`
  - Billing (Stripe): `src/rlcoach/api/routers/billing.py`
  - GDPR: `src/rlcoach/api/routers/gdpr.py`
- **DB models & migrations:** `src/rlcoach/db/models.py`, `migrations/versions/`.
  - Includes User, OAuthAccount, Session, CoachSession/Message/Note, UploadedReplay, UserReplay.
- **Worker & pipeline integration:** `src/rlcoach/worker/tasks.py`
  - Runs replay parsing, writes JSON, persists results via `db/writer.py`, handles upload status + errors.

### 3.3 SaaS Frontend (Working, partial)

**Next.js App:** `frontend/src/app/`
- Dashboard routes in `frontend/src/app/(dashboard)/`.
- Upload flow: `frontend/src/components/UploadDropzone.tsx`.
- OAuth: `frontend/src/lib/auth.ts` (Discord + Google; Steam commented out).
- API proxy: `frontend/src/app/api/v1/[...path]/route.ts`.
- Stripe routes: `frontend/src/app/api/stripe/*`.

---

## 4) Plan-by-Plan Status (Detailed)

### 4.1 `IMPLEMENTATION_PLAN.md` (SaaS Transformation)

**Phase 1: Infrastructure Foundation**
- Code artifacts exist: Dockerfiles, nginx config, env examples, CI/CD workflows, backup scripts.
- `docker-compose.prod.yml` includes `SAAS_MODE`, `ENVIRONMENT`, `BACKEND_URL`.
- **Status in plan:** marked complete in doc for Phase 1 tasks.

**Phase 2: PostgreSQL Migration**
- Models updated with SaaS tables in `src/rlcoach/db/models.py`.
- Alembic migration files exist: `migrations/versions/20260103_001_initial_schema.py`, `20260104_002_add_free_coach_preview.py`.
- **Plan checklist is still unchecked**, but code indicates core schema is implemented.

**Phase 3: Auth & Authorization**
- NextAuth JWT flow implemented in `frontend/src/lib/auth.ts`.
- Bootstrap endpoint exists: `/api/v1/users/bootstrap`.
- JWT signed with `NEXTAUTH_SECRET` in session callback.
- **Gaps:** Steam provider disabled; Epic OAuth not present; NextAuth Postgres adapter not wired (uses JWT).

**Phase 4: Replay Upload & Processing**
- Upload endpoint exists: `POST /api/v1/replays/upload`.
- Worker pipeline persists analysis via `db/writer.py`.
- Backpressure and disk checks exist in worker (`check_disk_usage`).
- **Gaps:** Real-time progress over websockets/SSE not implemented; relies on polling.

**Phase 5: Dashboard Frontend**
- Pages implemented:
  - Dashboard home `frontend/src/app/(dashboard)/page.tsx`
  - Replays list/detail
  - Sessions
  - Trends
  - Compare
  - Coach
  - Settings
- **Gaps:** Visuals are custom but not aligned to the full UX polish plan; some UI inlines still exist; real-time charts via Recharts not present.

**Phase 6: Stripe Payments**
- Stripe endpoints exist in backend; frontend upgrade + portal routes exist.
- Webhook handler present (`/stripe/webhook`).
- **Gaps:** Production verification, graceful payment failure handling, and formal plan checklist still open.

**Phase 7: AI Coach**
- Claude Opus 4.5 integration exists in `src/rlcoach/api/routers/coach.py`.
- Tools + prompts live in `src/rlcoach/services/coach/`.
- Free preview logic exists (1 message) and token budget tracking is wired.
- **Gaps:** Streaming endpoint not implemented (UX plan expects it); structured review sessions not implemented.

**Phase 8: Polish, Testing & Launch**
- Legal pages exist (`frontend/src/app/privacy`, `terms`).
- **Gaps:** E2E tests, load testing, security audit, monitoring/alerting, and official launch checklist are not complete.

---

### 4.2 `SAAS_FIXES_PLAN.md` (Critical SaaS Loop)

**Phase 1–5:** All tasks are checked in plan and appear implemented in code:
- DB initialization with `DATABASE_URL` and `SAAS_MODE` handling.
- OAuth bootstrap endpoint and NextAuth integration.
- Replay persistence + UserReplay creation in worker.
- Schema mismatch fixes (bcpm/supersonic, win/loss casing, size limits).
- Dashboard wired to real endpoints (replays, sessions, trends, compare).

**Phase 6:** **NOT DONE**
- Process 10 replays from `/replays` (E2E).
- Verify dashboard data end-to-end.
- Run quality gates (pytest, ruff, black).
- Final Codex review.

---

### 4.3 `UX_IMPLEMENTATION_PLAN.md`

**Phase 1 (Critical fixes):** Mostly implemented:
- Dashboard uses real `/api/v1/users/me/dashboard`.
- Upload polling/backoff and retry exists in `UploadDropzone`.
- Free coach preview implemented.

**Phase 2 (Error handling):** Partially implemented:
- ErrorBoundary exists and is used in dashboard layout.
- More granular error mapping and toast system exists, but not fully standardized across the app.

**Phase 3 (Onboarding & landing):** Not implemented in code:
- No onboarding tour component.
- Landing page enhancements (testimonials, FAQ, demo embed) not present.

**Phase 4 (Streaming coach):** Not implemented:
- No `/api/v1/coach/chat/stream` endpoint.
- No streaming client hook or SSE UI.

**Phase 5 (UI component library):** Partial:
- Toast exists; shared Button/Input/Card library incomplete.
- Many pages still use inline Tailwind patterns.

**Phase 6 (Rank benchmarks):** Partial:
- Benchmark model + compare endpoint exist.
- Data only for C2–SSL doubles in `data/benchmarks/gc_benchmarks_2v2.json`.

**Phase 7 (Multi-game trends):** Partial:
- Trends endpoint exists and supports metrics/time ranges.
- UI aggregates data but does not match planned charting/insight depth.

**Phase 8 (Cause-effect insights):** Not implemented.

---

### 4.4 `MECHANICS_IMPLEMENTATION_PLAN_v2.md`

- Most mechanics appear implemented in `src/rlcoach/analysis/mechanics.py`:
  - wavedash, speedflip, musty, ceiling shot, double touch, dribble, skim, psycho, etc.
- **Planned but missing:** confidence scoring, air-roll TAP vs HELD distinction, and speed-dependent thresholds for flip reset.

---

### 4.5 `codex/Plans/rlcoach_implementation_plan.md` (Local Pipeline)

**Implemented:**
- Pluggable adapter interface, normalization, events, analyzers, JSON schema, Markdown output, CLI viewer.

**Remaining gaps:**
- Rust adapter robustness still needs hardening (player identity mapping, classification across builds).
- CRC verification remains stubbed; report warns “CRC not verified (stubbed)”.

---

## 5) Critical Gaps & Blockers

1. **Rust adapter robustness**
- Players are present for `testing_replay.replay`, and a headerless fallback index was added on 2026-02-02 to avoid empty player arrays.
- Mapping still relies on team order rather than PRI/Reservation linkage, so per-player identity can still be wrong in some replays.
- Next hardening step: PRI/Reservation-based mapping to unique IDs.

2. **E2E SaaS verification**
   - Phase 6 in `SAAS_FIXES_PLAN.md` has not been completed.
   - No documented full end-to-end run with uploads, processing, dashboard, and coach flow.

3. **Streaming coach**
   - UX plan expects streaming (SSE). Currently only non-streaming chat.

4. **Benchmarks completeness**
   - Only partial rank data (C2–SSL doubles). No full rank coverage or 1v1/3v3.

5. **Plan/doc staleness**
   - `IMPLEMENTATION_PLAN.md` and `UX_IMPLEMENTATION_PLAN.md` checkboxes do not reflect code reality.

---

## 6) Tests & Quality Gates (Current Reality)

- Pytest exists with significant coverage (`tests/`), including Rust adapter integration tests in `tests/test_rust_adapter.py`.
- Ballchasing parity harnesses and fixtures have been removed; there is no parity gating in the suite.
- Quality gates defined in `CONTEXT.md`:
  - `PYTHONPATH=src pytest -q`
  - `ruff check src/`
  - `black --check src/`
- README mentions 261 tests; `CONTEXT.md` mentions 388 tests (likely stale). Needs reconciliation.

---

## 7) Key Directories

- `src/rlcoach/` — core pipeline + SaaS backend
- `frontend/` — Next.js app
- `parsers/rlreplay_rust/` — Rust replay adapter
- `schemas/` — JSON schema
- `tests/` — pytest suite
- `codex/Plans/` — canonical pipeline plan
- `codex/docs/` — engineering docs (should include this master status doc)

---

## 8) Concrete Next Steps (Recommended)

1. **Parser robustness**
   - Implement fallback player indexing when header `PlayerStats` missing.
   - Improve car/ball classification patterns.
   - Add or refine mapping using PRI/Reservation if possible.

2. **E2E SaaS verification**
   - Process 10 replays from `/replays/`, verify dashboard metrics and coach flow.
   - Run quality gates and record results.

3. **Plan refresh**
   - Update `IMPLEMENTATION_PLAN.md` and `UX_IMPLEMENTATION_PLAN.md` checklists to reflect real status.

4. **Streaming coach**
   - Add SSE endpoint + client hook, per UX plan.

5. **Benchmarks data expansion**
   - Populate ranks beyond C2–SSL and add other playlists.

---

## 9) Notes on the Rust Adapter Issue (Historical)

- `codex/docs/network-frames-integration-issue.md` documents the original “empty players array” bug.
- Current code yields players for `testing_replay.replay` and includes a headerless fallback index in the Rust adapter to prevent empty player arrays.
- Mapping is still fragile for identity; a PRI/Reservation-based mapping is the recommended follow-up.

---

## 10) Command Cheatsheet

```bash
# Activate venv
source .venv/bin/activate

# Run tests
PYTHONPATH=src pytest -q

# Lint & format
ruff check src/
black --check src/

# Build Rust adapter
make rust-dev

# Generate report JSON
python -m rlcoach.cli analyze Replay_files/testing_replay.replay --adapter rust --out out --pretty

# Generate JSON + Markdown dossier
python -m rlcoach.cli report-md Replay_files/testing_replay.replay --adapter rust --out out --pretty
```
