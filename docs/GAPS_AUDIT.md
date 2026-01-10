# RLCoach SaaS Implementation Gaps Audit

**Date:** 2026-01-10
**Auditor:** Claude Opus 4.5
**Status:** CRITICAL - Dashboard non-functional

---

## Executive Summary

The RLCoach SaaS dashboard UI exists but is non-functional because:
1. **Dashboard pages use hardcoded mock data** instead of calling real APIs
2. **Worker doesn't persist replay analysis** to the database
3. **API endpoints missing or mismatched** with frontend expectations
4. **Authentication flow incomplete** for dev/credentials login

The user can log in but sees empty/mock dashboards because no real data flows through the system.

---

## Spec vs Reality: Dashboard Pages

### Page Status Overview

| Page | Spec | UI Built | API Wired | Data Flows | Status |
|------|------|----------|-----------|------------|--------|
| Home | Hero mechanics + topline stats | Yes | **NO** | **NO** | BROKEN |
| Replay List | Sortable/filterable table | Yes | **NO** | **NO** | BROKEN |
| Replay Detail | 7 tabs deep dive | Yes | **NO** | **NO** | BROKEN |
| Sessions | Grouped by play session | Yes | **NO** | **NO** | BROKEN |
| Trends | Stats over time | Yes | **NO** | **NO** | BROKEN |
| Compare | Rank + self comparison | Yes | **NO** | **NO** | BROKEN |
| Settings | Profile, accounts, prefs | Partial | Partial | Partial | PARTIAL |

### Home Page (`/`)

**Spec Requirements:**
- Mechanics breakdown with rank comparisons ("47 flip resets - top 3% for Diamond")
- Topline stats: goals, assists, saves, shots (large)
- Secondary stats: boost/100, avg speed, third splits (smaller)
- Screenshot-worthy design

**Current State:**
- File: `frontend/src/app/(dashboard)/page.tsx`
- Uses hardcoded `mockStats` and `mockMechanics` objects
- No API call to fetch real data
- No empty state for new users

**Gap:** Complete - needs full API wiring

### Replay List Page (`/replays`)

**Spec Requirements:**
- All uploaded replays in sortable table
- Columns: date, result, score, map, playlist
- Filter by playlist, date range, result
- Infinite scroll or pagination

**Current State:**
- File: `frontend/src/app/(dashboard)/replays/page.tsx`
- Shows "Please sign in to view your replays" (auth now fixed)
- When signed in, calls API but expects `result` and `score` fields
- Backend doesn't return these fields

**Gap:** API contract mismatch + missing fields in response

### Replay Detail Page (`/replays/[id]`)

**Spec Requirements (7 tabs):**
1. Overview: game result, scoreboard, hero stats
2. Mechanics: counts, timestamps, success rates
3. Boost: pickups, efficiency, time at 0/100
4. Positioning: heatmaps, rotation, third splits
5. Timeline: interactive events
6. Defense: saves, clears, shadow defense
7. Offense: shots, xG, assists

**Current State:**
- File: `frontend/src/app/(dashboard)/replays/[id]/page.tsx`
- Uses mock data objects
- Tab structure exists but not wired to real data

**Gap:** Complete - needs API wiring for all 7 tabs

### Sessions Page (`/sessions`)

**Spec Requirements:**
- Replays grouped by play session (30-min gap)
- Session card with date, duration, W-L, key stats
- Expandable to see individual replays

**Current State:**
- File: `frontend/src/app/(dashboard)/sessions/page.tsx`
- Uses mock data
- `session_detection.py` service NOT CREATED

**Gap:** Missing backend service + API + frontend wiring

### Trends Page (`/trends`)

**Spec Requirements:**
- Line charts for metrics over time
- X-axis toggle: session/time/replay granularity
- Date range selector

**Current State:**
- File: `frontend/src/app/(dashboard)/trends/page.tsx`
- Calls `/api/v1/analysis/trends` - WRONG PATH
- Analysis router disabled in SaaS mode
- Uses mock data as fallback

**Gap:** Wrong API path + disabled endpoint + needs real data

### Compare Page (`/compare`)

**Spec Requirements:**
- Tab 1: Your stats vs rank average
- Tab 2: This week vs last week
- Radar/bar chart visualization

**Current State:**
- File: `frontend/src/app/(dashboard)/compare/page.tsx`
- Uses mock data
- No API endpoints exist for comparison

**Gap:** Missing API endpoints + frontend wiring

---

## Data Pipeline Gaps

### 1. Worker Doesn't Persist Analysis

**Location:** `src/rlcoach/worker/tasks.py:171-196`

**Problem:** Worker processes replays but:
- Only writes JSON file to disk
- Only updates `UploadedReplay` status
- Does NOT write to `Replay` or `PlayerGameStats` tables
- Dashboard queries return empty because tables are empty

**Impact:** CRITICAL - All dashboards empty

### 2. No Session Detection Service

**Location:** `src/rlcoach/services/session_detection.py` - FILE DOES NOT EXIST

**Spec:** "Replays within 30 minutes = same session"

**Impact:** Sessions page cannot function

### 3. No Replay Ownership Service

**Location:** `src/rlcoach/services/replay_ownership.py` - FILE DOES NOT EXIST

**Spec:** "Auto-match replays to user based on platform ID"

**Impact:** Replays not linked to users properly

---

## API Contract Mismatches

### 1. Replays List Response

**Frontend expects (replays/page.tsx):**
```typescript
{
  id: string,
  date: string,
  result: "WIN" | "LOSS" | "DRAW",  // MISSING
  score: string,                      // MISSING
  map: string,
  playlist: string
}
```

**Backend returns (routers/replays.py):**
```python
{
  id: str,
  uploaded_at: datetime,
  filename: str,
  status: str
  # NO result, score, map, playlist
}
```

### 2. Dashboard Stats Endpoint

**Frontend expects:** `GET /api/v1/dashboard/stats`
**Backend has:** `GET /api/v1/dashboard/home` (different structure)

### 3. Trends Endpoint

**Frontend calls:** `/api/v1/analysis/trends`
**Backend has:** `/analysis/trends` (no /api/v1 prefix, disabled in SaaS)

### 4. Compare Endpoints

**Frontend expects:**
- `GET /api/v1/compare/rank`
- `GET /api/v1/compare/self`

**Backend has:** Neither endpoint exists

### 5. Sessions Endpoint

**Frontend expects:** `GET /api/v1/sessions`
**Backend has:** Endpoint exists but returns wrong structure

---

## Authentication Gaps (Mostly Fixed)

### Fixed Issues
- [x] `getToken()` replaced with `auth()` in proxy route
- [x] `rewrites()` removed from next.config.js
- [x] Dev-login provider working

### Remaining Issues
- [ ] Bootstrap endpoint may not create users properly for credentials provider
- [ ] `providerAccountId` handling for dev-login may be inconsistent

---

## Missing Backend Services

| Service | Spec Location | File | Status |
|---------|--------------|------|--------|
| Session Detection | Phase 2.6 | `services/session_detection.py` | NOT CREATED |
| Replay Ownership | Phase 2.5 | `services/replay_ownership.py` | NOT CREATED |
| Rank Benchmarks | Phase 5.14.1 | `services/benchmarks.py` | INCOMPLETE |
| Compare Rank | Phase 5.14 | API endpoint | NOT CREATED |
| Compare Self | Phase 5.14 | API endpoint | NOT CREATED |

---

## Database Schema Gaps

### 1. Missing Result/Score Fields

**Problem:** `Replay` table doesn't store game result or score in a way frontend can easily query.

**Impact:** Replay list can't show WIN/LOSS/score.

### 2. Session Assignment

**Problem:** No `session_id` field on replays or separate sessions table for grouping.

**Impact:** Sessions page can't group replays.

### 3. Benchmark References

**Problem:** `users.py:618-626` references columns that don't exist in `PlayerGameStats`.

**Impact:** Benchmark endpoint will crash.

---

## Frontend-Specific Gaps

### 1. Mock Data in Components

Files still using hardcoded mock data:
- `frontend/src/app/(dashboard)/page.tsx` - Home
- `frontend/src/app/(dashboard)/replays/page.tsx` - Replay list
- `frontend/src/app/(dashboard)/replays/[id]/page.tsx` - Replay detail
- `frontend/src/app/(dashboard)/sessions/page.tsx` - Sessions
- `frontend/src/app/(dashboard)/trends/page.tsx` - Trends
- `frontend/src/app/(dashboard)/compare/page.tsx` - Compare

### 2. Missing Loading States

Most pages lack proper loading skeletons.

### 3. Missing Empty States

No "Upload your first replay" messaging for new users.

---

## Priority Fix Order

### P0 - Critical (Dashboard Non-Functional)

1. **Worker: Persist replay analysis to database**
   - Write to `Replay` and `PlayerGameStats` tables
   - Required for ANY dashboard data to appear

2. **API: Add result/score to replay responses**
   - Compute from PlayerGameStats
   - Return in list and detail endpoints

3. **Frontend: Wire pages to real APIs**
   - Remove mock data
   - Add loading/empty states

### P1 - High (Features Missing)

4. **Create session detection service**
   - Group replays by 30-min gap
   - Expose via API

5. **Create compare endpoints**
   - Rank comparison
   - Self comparison (period over period)

6. **Fix trends endpoint**
   - Enable in SaaS mode
   - Correct API path

### P2 - Medium (Polish)

7. **Create replay ownership service**
   - Auto-match by platform ID

8. **Add rank benchmarks**
   - Per-rank stat aggregates

9. **Add skeleton loading components**

10. **Add onboarding tour for new users**

---

## Estimated Effort

| Priority | Items | Effort |
|----------|-------|--------|
| P0 | 3 items | 1-2 days |
| P1 | 3 items | 2-3 days |
| P2 | 4 items | 2-3 days |
| **Total** | **10 items** | **5-8 days** |

---

## Next Steps

1. Create detailed implementation plan with file paths and code changes
2. Get Codex/Gemini review of plan
3. Create tickets for parallel execution
4. Implement with subagents
5. Test end-to-end flow
6. Verify all 7 dashboard pages functional
