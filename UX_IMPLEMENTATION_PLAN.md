# UX Polish Implementation Plan

**Spec:** `docs/plans/2026-01-04-ux-polish-spec.md`
**Created:** 2026-01-04
**Status:** In Progress
**Last Updated:** 2026-02-02

---

## Phase Overview

| Phase | Name | Status | Priority |
|-------|------|--------|----------|
| 1 | Critical Fixes | [~] In Progress | P0 |
| 2 | Error Handling | [~] In Progress | P0 |
| 3 | Onboarding & Landing | [ ] Not Started | P1 |
| 4 | Streaming Coach | [ ] Not Started | P1 |
| 5 | UI Component Library | [~] In Progress | P1 |
| 6 | Rank Benchmarks | [~] In Progress | P2 |
| 7 | Multi-Game Trending | [~] In Progress | P2 |
| 8 | Cause-Effect Insights | [ ] Not Started | P2 |

---

## Phase 1: Critical Fixes

### 1.1 Remove Mock Data from Dashboard
**Files:**
- `frontend/src/app/(dashboard)/page.tsx`

**Tasks:**
- [x] Remove `mockStats` and `mockMechanics` objects
- [x] Add API call to fetch real stats: `GET /api/v1/users/me/dashboard`
- [x] Add loading state while fetching
- [ ] Add empty state when no replays: "Upload your first replay to see stats"
- [x] Handle API errors gracefully

**Backend (if needed):**
- [x] Create `GET /api/v1/users/me/dashboard` endpoint
- [x] Return: total replays, win rate, recent mechanics, recent stats

### 1.2 Upload Success Flow
**Files:**
- `frontend/src/components/layout/UploadModal.tsx`
- `frontend/src/components/UploadDropzone.tsx`

**Tasks:**
- [x] Add success toast component (temporary inline, extract in Phase 5)
- [x] On upload complete: show "Analysis ready! View replay" toast
- [ ] Add "View Replay" button that navigates to `/dashboard/replays/[id]`
- [ ] Track first upload in localStorage for celebration

### 1.3 Coach Preview for Free Users
**Files:**
- `frontend/src/app/(dashboard)/coach/page.tsx`
- `src/rlcoach/api/routers/coach.py`
- `src/rlcoach/db/models.py`

**Tasks:**
- [x] Add `free_coach_message_used` boolean to User model
- [x] Create migration for new field
- [x] Modify coach chat endpoint: allow 1 message for free users
- [x] Frontend: check user's free message status
- [x] After free message: show upgrade prompt inline
- [x] Pro users: no change

### 1.4 Upload Progress & Retry
**Files:**
- `frontend/src/components/UploadDropzone.tsx`

**Tasks:**
- [ ] Show "Analyzing... typically 30 seconds" during processing
- [x] Implement exponential backoff: 2s → 5s → 10s → 30s
- [x] On timeout (5 min total): show "Still processing" with options
- [x] Add "Retry Upload" button for failed uploads
- [ ] Add "Check Status" button that re-polls

**Verification:**
```bash
# Frontend compiles
cd frontend && npm run build

# Backend tests pass
source .venv/bin/activate && PYTHONPATH=src pytest -q
```

---

## Phase 2: Error Handling

### 2.1 Global Error Boundary
**Files:**
- `frontend/src/components/ErrorBoundary.tsx` (new)
- `frontend/src/app/layout.tsx`

**Tasks:**
- [x] Create ErrorBoundary component with friendly UI
- [x] Include "Try Again" button that reloads
- [x] Include "Go Home" button
- [x] Wrap app in ErrorBoundary at layout level
- [x] Log errors to console (dev) / future service (prod)

### 2.2 Coach Page Error States
**Files:**
- `frontend/src/app/(dashboard)/coach/page.tsx`

**Tasks:**
- [x] Wrap coach content in error boundary
- [x] Handle 402 (budget exhausted) with helpful message
- [ ] Handle 503 (service unavailable) with retry option
- [x] Handle network errors with offline message
- [x] Show budget remaining prominently

### 2.3 Settings Page Feedback
**Files:**
- `frontend/src/app/(dashboard)/settings/page.tsx`

**Tasks:**
- [x] Add loading state for "Manage Subscription" button
- [ ] Show error toast if portal creation fails
- [ ] Add success feedback before redirect

### 2.4 Error Message Mapping
**Files:**
- `frontend/src/lib/errors.ts` (new)

**Tasks:**
- [x] Create error code → friendly message map
- [x] Map OAuth errors to helpful messages
- [x] Map API errors to user-friendly text
- [x] Include "Contact support" for persistent errors

**Verification:**
```bash
cd frontend && npm run build && npm run lint
```

---

## Phase 3: Onboarding & Landing

### 3.1 First-Time User Tour
**Files:**
- `frontend/src/components/OnboardingTour.tsx` (new)
- `frontend/src/app/(dashboard)/layout.tsx`

**Tasks:**
- [ ] Create OnboardingTour component with tooltip steps
- [ ] Step 1: "Welcome! Upload a replay" (highlight upload button)
- [ ] Step 2: "Your stats appear here" (dashboard home)
- [ ] Step 3: "Deep dive into replays" (replays nav)
- [ ] Step 4: "Track progress over time" (trends nav)
- [ ] Step 5: "Get AI coaching" (coach nav, mention Pro)
- [ ] Store `tour_completed` in localStorage
- [ ] Add "Skip Tour" button
- [ ] Don't repeat after completion

### 3.2 Landing Page Improvements
**Files:**
- `frontend/src/app/page.tsx`

**Tasks:**
- [ ] Add Testimonials section (3 testimonials with rank progression)
- [ ] Add FAQ section (5 common questions)
- [ ] Change "Get Started" to "Start Free" (differentiate from Sign In)
- [ ] Add video embed or animated demo GIF
- [ ] Add user count if available (or remove if not impressive)

### 3.3 Skeleton Components
**Files:**
- `frontend/src/components/ui/Skeleton.tsx` (new)
- `frontend/src/app/(dashboard)/page.tsx`
- `frontend/src/app/(dashboard)/replays/page.tsx`

**Tasks:**
- [ ] Create base Skeleton component with shimmer animation
- [ ] Create SkeletonCard variant
- [ ] Create SkeletonStat variant
- [ ] Create SkeletonList variant
- [ ] Apply to dashboard stats loading
- [ ] Apply to replay list loading

**Verification:**
```bash
cd frontend && npm run build && npm run lint
```

---

## Phase 4: Streaming Coach Responses

### 4.1 Backend SSE Endpoint
**Files:**
- `src/rlcoach/api/routers/coach.py`
- `src/rlcoach/services/coach/streaming.py` (new)

**Tasks:**
- [ ] Create `POST /api/v1/coach/chat/stream` endpoint
- [ ] Use `StreamingResponse` from FastAPI
- [ ] Stream Claude tokens as SSE events
- [ ] Format: `data: {"token": "...", "done": false}\n\n`
- [ ] Final event: `data: {"done": true, "message_id": "...", "tokens_used": ...}\n\n`
- [ ] Handle errors mid-stream gracefully
- [ ] Token counting still works (count on completion)

### 4.2 Frontend Streaming UI
**Files:**
- `frontend/src/app/(dashboard)/coach/page.tsx`
- `frontend/src/lib/streaming.ts` (new)

**Tasks:**
- [ ] Create useStreamingChat hook
- [ ] Parse SSE events and append to message
- [ ] Show typing indicator during stream
- [ ] Add cursor/caret at end of streaming text
- [ ] Add "Stop generating" button
- [ ] Fallback to non-streaming on error
- [ ] Auto-scroll as content grows

**Verification:**
```bash
# Backend tests
source .venv/bin/activate && PYTHONPATH=src pytest tests/test_coach.py -q

# Frontend builds
cd frontend && npm run build
```

---

## Phase 5: UI Component Library

### 5.1 Button Component
**Files:**
- `frontend/src/components/ui/Button.tsx` (new)

**Tasks:**
- [ ] Create Button component with variants: primary, secondary, ghost, danger
- [ ] Add sizes: sm, md, lg
- [ ] Add states: loading (with spinner), disabled
- [ ] Migrate existing buttons to use component

### 5.2 Input Component
**Files:**
- `frontend/src/components/ui/Input.tsx` (new)

**Tasks:**
- [ ] Create Input component with label support
- [ ] Add hint text support
- [ ] Add error state with message
- [ ] Add aria-describedby for accessibility
- [ ] Migrate existing inputs

### 5.3 Card Component
**Files:**
- `frontend/src/components/ui/Card.tsx` (new)

**Tasks:**
- [ ] Create Card component with variants: default, stat, action
- [ ] Consistent padding, borders, shadows
- [ ] Migrate existing cards

### 5.4 Toast Component
**Files:**
- `frontend/src/components/ui/Toast.tsx` (new)
- `frontend/src/lib/toast.ts` (new)

**Tasks:**
- [ ] Create Toast component with types: success, error, warning, info
- [ ] Create toast context/provider
- [ ] Auto-dismiss with configurable duration
- [ ] Stack multiple toasts
- [ ] Accessible announcements (aria-live)
- [ ] Add dismiss button

### 5.5 Migration Pass
**Tasks:**
- [ ] Update all pages to use new components
- [ ] Remove inline Tailwind button/input/card patterns
- [ ] Ensure consistency across app

**Verification:**
```bash
cd frontend && npm run build && npm run lint
```

---

## Phase 6: Rank Benchmarks

### 6.1 Benchmark Data
**Files:**
- `src/rlcoach/analysis/benchmarks.py` (new or update existing)
- `src/rlcoach/api/routers/benchmarks.py` (new)

**Tasks:**
- [x] Define benchmark data structure
- [ ] Add estimates for all ranks (Bronze → SSL)
- [ ] Metrics: goals, assists, saves, shooting%, bcpm, avg_boost, etc.
- [~] Create `GET /api/v1/benchmarks/{rank}/{mode}` endpoint
  - Status note: Benchmarks currently served via `GET /api/v1/users/me/benchmarks` with partial rank coverage (C2–SSL 2v2).

### 6.2 Dashboard Integration
**Files:**
- `frontend/src/app/(dashboard)/page.tsx`

**Tasks:**
- [x] Fetch user's estimated rank (or use self-reported)
- [x] Fetch benchmarks for that rank
- [ ] Show comparison: "Your stat: X (Rank avg: Y)"
- [ ] Visual indicators: ↑ above avg, ↓ below avg, = on par

### 6.3 Insights Integration
**Files:**
- `src/rlcoach/analysis/insights.py`

**Tasks:**
- [ ] Update insight generation to include benchmark context
- [ ] "Your shooting is 15% (Diamond avg: 18%)"
- [ ] Severity tied to deviation from benchmark

**Verification:**
```bash
source .venv/bin/activate && PYTHONPATH=src pytest -q
```

---

## Phase 7: Multi-Game Trending

### 7.1 Trend API
**Files:**
- `src/rlcoach/api/routers/trends.py` (update)

**Tasks:**
- [x] Ensure trend endpoint returns real data
- [x] Support time ranges: 7d, 30d, 90d, all
- [x] Support metrics: win_rate, goals, assists, bcpm, mechanics
- [x] Handle insufficient data gracefully

### 7.2 Frontend Visualization
**Files:**
- `frontend/src/app/(dashboard)/trends/page.tsx`

**Tasks:**
- [x] Replace mock data with real API calls
- [x] Add time range selector
- [x] Add metric selector
- [ ] Show trend charts with Recharts
- [ ] Add empty state for insufficient data

### 7.3 Progress Indicators
**Tasks:**
- [ ] Calculate week-over-week changes
- [ ] Show ↑ X% or ↓ X% indicators
- [ ] Highlight significant improvements
- [ ] Add milestone celebrations (first 100 games, etc.)

**Verification:**
```bash
cd frontend && npm run build
source .venv/bin/activate && PYTHONPATH=src pytest -q
```

---

## Phase 8: Cause-Effect Insights

### 8.1 Enhanced Insight Engine
**Files:**
- `src/rlcoach/analysis/insights.py`

**Tasks:**
- [ ] Refactor insight generation for depth
- [ ] Include specific data points in insights
- [ ] Add "why" explanations
- [ ] Add concrete recommendations
- [ ] Example: "4 of 7 shots from >2200 UU — move closer before shooting"

### 8.2 Insight Priority System
**Files:**
- `src/rlcoach/analysis/insights.py`

**Tasks:**
- [ ] Add priority scoring to insights
- [ ] Factors: impact on win rate, deviation from benchmark, frequency
- [ ] Sort insights by priority
- [ ] Visual hierarchy in UI

### 8.3 Coach Session Recap
**Files:**
- `src/rlcoach/api/routers/coach.py`
- `frontend/src/app/(dashboard)/coach/page.tsx`

**Tasks:**
- [ ] Add `POST /api/v1/coach/sessions/{id}/recap` endpoint
- [ ] Generate structured summary: strengths, weaknesses, action items
- [ ] Frontend: show "Generate Summary" after 3+ messages
- [ ] Display structured recap card
- [ ] Add copy/share functionality

**Verification:**
```bash
source .venv/bin/activate && PYTHONPATH=src pytest -q
cd frontend && npm run build
```

---

## Quality Gates (All Phases)

```bash
# Python
source .venv/bin/activate
PYTHONPATH=src pytest -q
ruff check src/
black --check src/

# Frontend
cd frontend
npm run build
npm run lint
```

---

## Codex Checkpoints

1. [ ] After spec review (before implementation)
2. [ ] After Phase 1 (Critical Fixes)
3. [ ] After Phase 4 (Streaming Coach)
4. [ ] After Phase 5 (UI Components)
5. [ ] After Phase 8 (Final)

---

## Progress Log

### 2026-01-04
- Created spec document
- Created implementation plan
- Starting Phase 1...
