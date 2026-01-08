# SaaS Fixes Implementation Plan

**Status:** In Progress
**Created:** 2026-01-08
**Source:** Codex code review findings

---

## Overview

This plan addresses critical blockers preventing the SaaS product from functioning end-to-end. The core issues are:

1. **DB initialization** - SaaS mode doesn't connect to PostgreSQL
2. **Auth user persistence** - Users aren't created in Postgres on OAuth login
3. **Replay persistence** - Worker doesn't persist analysis to Replay/PlayerGameStats tables
4. **Schema mismatches** - Endpoints reference non-existent columns
5. **Mock data** - Dashboard pages don't call real APIs

**Goal:** Complete the SaaS loop: Sign-in → Upload → Process → Dashboard → Coach

---

## Phase 1: Fix Database Initialization

**Goal:** Ensure SaaS mode connects to PostgreSQL via DATABASE_URL

### Tasks

- [x] **1.1 Fix app.py lifespan handler**
  - File: `src/rlcoach/api/app.py`
  - Issue: Always tries local config, ignores DATABASE_URL
  - Fix: Check DATABASE_URL first, fall back to config file
  - Verification: App starts with DATABASE_URL set, connects to Postgres

- [x] **1.2 Add SAAS_MODE environment handling**
  - File: `src/rlcoach/api/app.py`
  - Issue: SAAS_MODE not consistently checked
  - Fix: Add explicit SAAS_MODE check in lifespan
  - Verification: CLI routers excluded when SAAS_MODE=true

- [x] **1.3 Update docker-compose.prod.yml**
  - File: `docker-compose.prod.yml`
  - Issue: Missing SAAS_MODE, ENVIRONMENT, BACKEND_URL
  - Fix: Add required environment variables
  - Verification: Production compose has all vars

### Phase 1 Verification
```bash
# Start with DATABASE_URL
DATABASE_URL=postgresql://user:pass@localhost:5432/rlcoach python -c "from rlcoach.api.app import app; print('OK')"
```

---

## Phase 2: Fix Auth User Persistence

**Goal:** Create users in Postgres on first OAuth login

### Tasks

- [x] **2.1 Add user bootstrap endpoint**
  - File: `src/rlcoach/api/routers/users.py`
  - Issue: Backend expects users to exist but NextAuth doesn't create them
  - Fix: Add POST /api/v1/users/bootstrap endpoint
  - Verification: Returns user record, creates if not exists

- [x] **2.2 Call bootstrap on NextAuth sign-in**
  - File: `frontend/src/lib/auth.ts`
  - Issue: No user creation on OAuth login
  - Fix: Call bootstrap endpoint in signIn callback
  - Verification: New OAuth login creates user in Postgres

- [x] **2.3 Fix JWT token format**
  - File: `frontend/src/app/api/v1/[...path]/route.ts`
  - Issue: May be using OAuth access token instead of signed JWT
  - Fix: Ensure proxy creates proper JWT with userId
  - Verification: Backend validates token, extracts userId

### Phase 2 Verification
```bash
# OAuth login should create user
# Check database: SELECT * FROM users WHERE id = '<user-id>';
```

---

## Phase 3: Fix Replay Persistence Pipeline

**Goal:** Worker persists analysis results to Replay, PlayerGameStats, Player tables

### Tasks

- [x] **3.1 Integrate db/writer.py in worker**
  - File: `src/rlcoach/worker/tasks.py`
  - Issue: Worker only writes JSON, doesn't call writer
  - Fix: After successful parse, call writer.store_analysis_results()
  - Verification: Replays appear in replays table

- [x] **3.2 Fix UserReplay FK constraint**
  - File: `src/rlcoach/worker/tasks.py`
  - Issue: Creates UserReplay before Replay exists
  - Fix: Create Replay first, then UserReplay
  - Verification: No FK violations on upload

- [x] **3.3 Handle player creation/lookup**
  - File: `src/rlcoach/db/writer.py`
  - Issue: May create duplicate players
  - Fix: Upsert players by platform_id
  - Verification: Same player in multiple replays = one Player row

### Phase 3 Verification
```bash
# Upload replay, check tables:
# SELECT COUNT(*) FROM replays;
# SELECT COUNT(*) FROM player_game_stats;
# SELECT COUNT(*) FROM players;
```

---

## Phase 4: Fix Schema Mismatches

**Goal:** Endpoints use correct column names

### Tasks

- [x] **4.1 Fix benchmarks endpoint**
  - File: `src/rlcoach/api/routers/users.py`
  - Issue: References boost_per_minute, supersonic_pct (don't exist)
  - Fix: Use bcpm, time_supersonic_s / game_duration
  - Verification: /api/v1/users/me/benchmarks returns data

- [x] **4.2 Fix GDPR endpoint**
  - File: `src/rlcoach/api/routers/gdpr.py`
  - Issue: References non-existent columns
  - Fix: Use correct column names
  - Verification: GDPR data export works

- [x] **4.3 Fix win/loss casing**
  - File: `src/rlcoach/api/routers/users.py`, `src/rlcoach/db/writer.py`
  - Issue: Writer uses uppercase, queries expect lowercase
  - Fix: Standardize to uppercase everywhere
  - Verification: Win rate calculations correct

- [x] **4.4 Fix upload size limits**
  - Files: `nginx/nginx.conf`, `frontend/src/lib/errors.ts`, `src/rlcoach/api/routers/replays.py`
  - Issue: Inconsistent limits (10MB vs 50MB)
  - Fix: Standardize to 50MB everywhere
  - Verification: 30MB replay uploads successfully

### Phase 4 Verification
```bash
# All endpoints return 200, not 500
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/v1/users/me/benchmarks
```

---

## Phase 5: Wire Dashboard to Real APIs

**Goal:** Dashboard pages fetch real data instead of mock data

### Tasks

- [x] **5.1 Fix replays list page**
  - File: `frontend/src/app/(dashboard)/replays/page.tsx`
  - Issue: Uses mock data
  - Fix: Fetch from /api/v1/replays
  - Verification: Shows real replays after upload

- [x] **5.2 Fix replay detail page**
  - File: `frontend/src/app/(dashboard)/replays/[id]/page.tsx`
  - Issue: Uses mock data
  - Fix: Fetch from /api/v1/replays/{id}
  - Verification: Shows real replay data

- [x] **5.3 Fix sessions page**
  - File: `frontend/src/app/(dashboard)/sessions/page.tsx`
  - Issue: Uses mock data
  - Fix: Fetch from /api/v1/sessions
  - Verification: Shows real sessions

- [x] **5.4 Fix trends page**
  - File: `frontend/src/app/(dashboard)/trends/page.tsx`
  - Issue: Calls /api/v1/analysis/trends which is disabled in SaaS
  - Fix: Enable trends endpoint in SaaS mode
  - Verification: Trends page shows real data

- [x] **5.5 Fix compare page**
  - File: `frontend/src/app/(dashboard)/compare/page.tsx`
  - Issue: Uses mock data
  - Fix: Fetch from /api/v1/compare endpoints
  - Verification: Compare page shows real comparisons

### Phase 5 Verification
```bash
# All dashboard pages show real data
# No "mock" or hardcoded arrays in page source
```

---

## Phase 6: End-to-End Verification

**Goal:** Complete flow works with real replays

### Tasks

- [ ] **6.1 Process test replays**
  - Run: Process 10 replays from /replays directory
  - Verification: All complete without errors

- [ ] **6.2 Verify dashboard data**
  - Check: Dashboard home shows real stats
  - Check: Replays list shows uploaded replays
  - Check: Replay detail shows mechanics/boost/positioning

- [ ] **6.3 Run quality gates**
  - Run: pytest, ruff check, black --check
  - Verification: All pass

- [ ] **6.4 Call Codex for final review**
  - Run: codex exec with final review prompt
  - Verification: "Ship it" verdict

---

## Completion Criteria

1. [ ] User can OAuth login and be created in Postgres
2. [ ] User can upload replay and see it processed
3. [ ] Dashboard shows real data from database
4. [ ] All quality gates pass
5. [ ] Codex final review passes
