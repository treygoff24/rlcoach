# Dashboard Fix Implementation Plan

**Date:** 2026-01-10
**Goal:** Make all 7 dashboard pages functional with real data
**Prerequisite:** Dev-login auth working (completed)

---

## Overview

The dashboard pages exist but display mock data. We need to:
1. Make the worker persist replay analysis to the database
2. Add missing fields to API responses
3. Wire frontend pages to real APIs
4. Create missing backend services

---

## Task 1: Worker Persist Replay Analysis (P0-CRITICAL)

**Problem:** Worker processes replays but doesn't write to `Replay` or `PlayerGameStats` tables.

**Files to modify:**
- `src/rlcoach/worker/tasks.py`

**Changes:**
1. After parsing replay, call `writer.write_replay()` to persist to DB
2. Store the Replay record with proper fields (result, score, map, playlist)
3. Store PlayerGameStats for each player
4. Then create UserReplay link

**Code approach:**
```python
# In process_replay_task after parsing:
from rlcoach.db.writer import DatabaseWriter
from rlcoach.db.session import create_session

with create_session() as session:
    writer = DatabaseWriter(session)
    replay_record = writer.write_replay(parsed_data)

    # Now create UserReplay link
    user_replay = UserReplay(
        user_id=user_id,
        replay_id=replay_record.id,
        ownership_type="uploaded"
    )
    session.add(user_replay)
    session.commit()
```

**Verification:**
- After upload, query `Replay` table - should have data
- Query `PlayerGameStats` - should have player stats

---

## Task 2: API - Add Result/Score to Replay Responses (P0)

**Problem:** Frontend expects `result` and `score` but backend doesn't return them.

**Files to modify:**
- `src/rlcoach/api/routers/replays.py`

**Changes:**
1. Add `result` field to ReplayResponse schema (compute from PlayerGameStats)
2. Add `score` field (format: "3-2")
3. Add `map_name` and `playlist` fields

**New response model:**
```python
class ReplayListItem(BaseModel):
    id: str
    uploaded_at: datetime
    filename: str
    status: str
    # Add these:
    result: Optional[str] = None  # "WIN", "LOSS", "DRAW"
    score: Optional[str] = None   # "3-2"
    map_name: Optional[str] = None
    playlist: Optional[str] = None
    duration_seconds: Optional[int] = None
```

**Query approach:**
- Join UploadedReplay → Replay → PlayerGameStats
- Filter PlayerGameStats where is_me=True OR match platform_id
- Compute result from team goals

---

## Task 3: Frontend - Wire Replay List to Real API (P0)

**Problem:** `/replays` page uses mock data.

**Files to modify:**
- `frontend/src/app/(dashboard)/replays/page.tsx`

**Changes:**
1. Remove mock data objects
2. Fetch from `/api/v1/replays/library` (existing endpoint)
3. Handle loading state with skeleton
4. Handle empty state for new users
5. Map API response to table columns

**Code approach:**
```typescript
const { data, isLoading, error } = useSWR('/api/v1/replays/library', fetcher);

if (isLoading) return <ReplayListSkeleton />;
if (!data?.replays?.length) return <EmptyState message="Upload your first replay!" />;
return <ReplayTable replays={data.replays} />;
```

---

## Task 4: Frontend - Wire Home Page Dashboard (P0)

**Problem:** Home page uses mock stats and mechanics.

**Files to modify:**
- `frontend/src/app/(dashboard)/page.tsx`

**Changes:**
1. Remove `mockStats` and `mockMechanics` objects
2. Fetch from `/api/v1/dashboard/stats` (need to create or use existing)
3. Add loading skeleton
4. Add empty state for new users

**API needed:**
- `GET /api/v1/users/me/stats` - aggregate stats
- Or enhance existing `/api/v1/dashboard/home`

---

## Task 5: Frontend - Wire Replay Detail Page (P0)

**Problem:** Replay detail page uses mock data for all 7 tabs.

**Files to modify:**
- `frontend/src/app/(dashboard)/replays/[id]/page.tsx`

**Changes:**
1. Fetch replay data from `/api/v1/replays/{id}`
2. Wire Overview tab to real data
3. Wire Mechanics tab to mechanics data
4. Wire Boost tab to boost stats
5. Wire other tabs (positioning, timeline, defense, offense)
6. Add loading/error states

---

## Task 6: Create Session Detection Service (P1)

**Problem:** `session_detection.py` doesn't exist, sessions page can't work.

**Files to create:**
- `src/rlcoach/services/session_detection.py`

**Logic:**
1. Get user's replays ordered by date
2. Group replays where gap < 30 minutes
3. Assign session_id to each replay
4. Return sessions with nested replays

**API to create/modify:**
- `GET /api/v1/sessions` - return sessions with nested replays

---

## Task 7: Frontend - Wire Sessions Page (P1)

**Problem:** Sessions page uses mock data.

**Files to modify:**
- `frontend/src/app/(dashboard)/sessions/page.tsx`

**Changes:**
1. Remove mock data
2. Fetch from `/api/v1/sessions`
3. Render session cards with expandable replay lists

---

## Task 8: Create Compare Endpoints (P1)

**Problem:** Compare page has no API endpoints.

**Files to create/modify:**
- `src/rlcoach/api/routers/compare.py` (new)
- `src/rlcoach/api/app.py` (add router)

**Endpoints:**
1. `GET /api/v1/compare/rank` - user stats vs rank average
2. `GET /api/v1/compare/self` - this period vs last period

---

## Task 9: Frontend - Wire Compare Page (P1)

**Problem:** Compare page uses mock data.

**Files to modify:**
- `frontend/src/app/(dashboard)/compare/page.tsx`

**Changes:**
1. Remove mock data
2. Fetch from compare endpoints
3. Render comparison visualizations

---

## Task 10: Fix Trends Endpoint (P1)

**Problem:** Trends endpoint disabled in SaaS mode, wrong path.

**Files to modify:**
- `src/rlcoach/api/app.py`
- `src/rlcoach/api/routers/analysis.py`

**Changes:**
1. Mount analysis router in SaaS mode (or create SaaS-specific trends endpoint)
2. Prefix with `/api/v1`
3. Return real trend data

---

## Task 11: Frontend - Wire Trends Page (P1)

**Problem:** Trends page uses mock data.

**Files to modify:**
- `frontend/src/app/(dashboard)/trends/page.tsx`

**Changes:**
1. Remove mock data
2. Fix API endpoint path
3. Render real trend charts

---

## Parallel Execution Plan

### Phase A (Parallel - Backend)
Run simultaneously with subagents:
- Task 1: Worker persist (CRITICAL)
- Task 2: API add result/score
- Task 6: Session detection service
- Task 8: Compare endpoints
- Task 10: Fix trends endpoint

### Phase B (Parallel - Frontend)
After Phase A, run simultaneously:
- Task 3: Wire replay list
- Task 4: Wire home page
- Task 5: Wire replay detail
- Task 7: Wire sessions page
- Task 9: Wire compare page
- Task 11: Wire trends page

### Phase C (Verification)
- Run all tests
- Manual testing of each page
- Fix any issues

---

## Verification Checklist

After implementation:
- [ ] Upload a replay → appears in database
- [ ] `/replays` shows real replay list with WIN/LOSS/score
- [ ] `/replays/[id]` shows real replay details with all tabs
- [ ] Home page shows real aggregate stats
- [ ] `/sessions` groups replays correctly
- [ ] `/trends` shows real trend charts
- [ ] `/compare` shows rank and self comparison
- [ ] All tests pass
- [ ] No mock data remains in dashboard pages

---

## Files Summary

### Backend Files to Modify
1. `src/rlcoach/worker/tasks.py` - persist analysis
2. `src/rlcoach/api/routers/replays.py` - add result/score
3. `src/rlcoach/api/routers/analysis.py` - fix trends
4. `src/rlcoach/api/app.py` - mount routers

### Backend Files to Create
5. `src/rlcoach/services/session_detection.py`
6. `src/rlcoach/api/routers/compare.py`

### Frontend Files to Modify
7. `frontend/src/app/(dashboard)/page.tsx` - home
8. `frontend/src/app/(dashboard)/replays/page.tsx` - list
9. `frontend/src/app/(dashboard)/replays/[id]/page.tsx` - detail
10. `frontend/src/app/(dashboard)/sessions/page.tsx`
11. `frontend/src/app/(dashboard)/trends/page.tsx`
12. `frontend/src/app/(dashboard)/compare/page.tsx`

---

## Estimated Timeline

| Phase | Tasks | Duration |
|-------|-------|----------|
| Phase A | Backend (5 tasks parallel) | 2-3 hours |
| Phase B | Frontend (6 tasks parallel) | 2-3 hours |
| Phase C | Verification | 1 hour |
| **Total** | | **5-7 hours** |

With aggressive parallelization using subagents, this can be completed in a single session.
