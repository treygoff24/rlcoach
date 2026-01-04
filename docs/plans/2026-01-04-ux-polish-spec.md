# UX Polish Spec — rlcoach SaaS

**Date:** 2026-01-04
**Status:** Draft
**Author:** Claude (Autonomous Build)

---

## Executive Summary

Transform rlcoach from a technically impressive but confusing product into a delightful, conversion-optimized SaaS. The core analysis engine is best-in-class; this spec focuses on removing friction from the path to "aha!" for new users.

**North Star Metric:** Activation Rate — % of signups who upload 3+ replays in first week.

---

## Problem Statement

### Current State
- Users sign up, see mock data on dashboard, get confused
- Upload a replay → processing completes → no feedback on what to do next
- Coach feature (main monetization) hidden behind paywall with no preview
- 99% estimated drop-off before users experience the value

### Desired State
- Clear onboarding flow: Upload → See Your Data → Understand It → Get Coaching
- Every user experiences the coach before being asked to pay
- Real data (not mock) throughout the dashboard
- Polished error handling and loading states

---

## Scope

### In Scope
1. **Critical UX fixes** — Mock data removal, upload success flow, coach preview
2. **Error handling** — Error boundaries, retry buttons, user-friendly messages
3. **Onboarding** — First-time user tour, landing page improvements
4. **Coach streaming** — Real-time token streaming via SSE
5. **UI component library** — Reusable Button, Input, Card, Toast, Skeleton
6. **Rank benchmarks** — Compare user stats to rank averages
7. **Multi-game trending** — Show improvement over time with real data
8. **Actionable insights** — Cause-effect analysis, not just descriptive stats

### Out of Scope (Future)
- Team management features
- Opponent scouting
- Training plan generator
- Mobile app
- GraphQL API
- B2B/enterprise features

---

## Detailed Requirements

### Phase 1: Critical Fixes

#### 1.1 Remove Mock Data from Dashboard
**Current:** Dashboard shows hardcoded `mockStats` with "247 replays" for new users.
**Required:**
- Replace mock data with real API calls to backend
- Show "Upload your first replay to see stats" when no replays exist
- Show actual counts, win rates, mechanics from user's data

**Acceptance Criteria:**
- [ ] New user sees "0 replays" not "247 replays"
- [ ] Stats reflect actual user data
- [ ] Empty state is helpful, not confusing

#### 1.2 Upload Success Flow
**Current:** Upload completes → status shows "completed" → user doesn't know what to do.
**Required:**
- Toast notification: "Analysis ready! View your replay"
- Auto-navigate option to replay detail page
- Clear CTA to view results

**Acceptance Criteria:**
- [ ] Success toast appears after processing completes
- [ ] User can click to view the analyzed replay
- [ ] First upload triggers special "first replay" celebration

#### 1.3 Coach Preview for Free Users
**Current:** Free users click Coach → redirect to /upgrade → no preview of value.
**Required:**
- Free users get 1 complimentary coach interaction
- After free message, show upgrade prompt with context
- Store `free_coach_used` flag in user model

**Acceptance Criteria:**
- [ ] Free user can send 1 message to coach
- [ ] After response, upgrade prompt explains value
- [ ] Flag prevents additional free messages
- [ ] Pro users unaffected

#### 1.4 Upload Progress & Retry
**Current:** 2-minute polling → "Processing timeout" with no retry.
**Required:**
- Show estimated time: "Analyzing... typically 30 seconds"
- On timeout: "Still processing. Check status later or retry"
- Retry button for failed uploads
- Exponential backoff for polling (2s → 5s → 10s → 30s)

**Acceptance Criteria:**
- [ ] Progress message shows during processing
- [ ] Timeout message is actionable
- [ ] Retry button works
- [ ] Polling doesn't hammer server

---

### Phase 2: Error Handling

#### 2.1 Global Error Boundary
**Required:**
- Wrap app in error boundary component
- Show friendly error UI with retry option
- Log errors for debugging (console in dev, service in prod)

**Acceptance Criteria:**
- [ ] Runtime errors show error UI, not blank screen
- [ ] User can retry or navigate away
- [ ] Errors are logged

#### 2.2 Coach Page Error States
**Required:**
- Handle API failures gracefully
- Show clear error messages with retry
- Handle token budget exhaustion with helpful message

**Acceptance Criteria:**
- [ ] API failure shows error, not blank screen
- [ ] "Budget exhausted" shows reset date and upgrade option
- [ ] Network errors are retriable

#### 2.3 Settings Page Feedback
**Current:** Clicking "Manage Subscription" catches errors silently.
**Required:**
- Show loading state during Stripe portal creation
- Show error toast if portal creation fails
- Confirm success with redirect

**Acceptance Criteria:**
- [ ] Loading spinner during portal creation
- [ ] Error message if it fails
- [ ] Success redirects to Stripe portal

#### 2.4 User-Friendly Error Messages
**Current:** Raw API errors shown to users ("OAuthCallback error").
**Required:**
- Map error codes to friendly messages
- Provide actionable next steps
- Include support contact for persistent errors

**Acceptance Criteria:**
- [ ] No raw error codes shown to users
- [ ] All errors have friendly messages
- [ ] Errors suggest next steps

---

### Phase 3: Onboarding & Landing Page

#### 3.1 First-Time User Tour
**Required:**
- Tooltip-based tour on first dashboard visit
- Highlight key sections: Upload, Stats, Replays, Trends, Coach
- "Skip tour" option
- Store `tour_completed` in localStorage

**Acceptance Criteria:**
- [ ] Tour triggers on first visit
- [ ] 5 tooltip steps explaining features
- [ ] Can be skipped
- [ ] Doesn't repeat after completion

#### 3.2 Landing Page Improvements
**Required:**
- Add testimonials section (2-3 with rank progression)
- Add user count if available
- Add FAQ section
- Fix CTA ambiguity ("Sign In" vs "Get Started")
- Add demo video or live preview widget

**Acceptance Criteria:**
- [ ] Social proof section visible
- [ ] FAQ answers common questions
- [ ] CTAs are clear and differentiated
- [ ] Demo section shows product value

#### 3.3 Skeleton Loading States
**Required:**
- Add skeleton components matching card layouts
- Use skeletons during data loading
- Apply to: dashboard stats, replay list, trends charts

**Acceptance Criteria:**
- [ ] No blank loading states
- [ ] Skeletons match final layout
- [ ] Smooth transition to real content

---

### Phase 4: Streaming Coach Responses

#### 4.1 Server-Sent Events (SSE) for Coach
**Required:**
- New endpoint: `POST /api/v1/coach/chat/stream`
- Stream tokens as Claude generates them
- Frontend handles streaming text display
- Fallback to non-streaming if SSE fails

**Acceptance Criteria:**
- [ ] Tokens appear as generated
- [ ] No waiting for full response
- [ ] Graceful fallback on error
- [ ] Token counting still works

#### 4.2 Streaming UI
**Required:**
- Typing indicator while streaming
- Cursor/caret at end of streaming text
- "Stop generating" button
- Smooth scroll as content grows

**Acceptance Criteria:**
- [ ] Visual feedback during generation
- [ ] Can stop generation early
- [ ] UI handles long responses gracefully

---

### Phase 5: UI Component Library

#### 5.1 Button Component
**Required:**
- Variants: primary, secondary, ghost, danger
- Sizes: sm, md, lg
- States: default, hover, active, disabled, loading
- Consistent styling across app

**Acceptance Criteria:**
- [ ] All buttons use Button component
- [ ] Consistent sizing and spacing
- [ ] Loading state with spinner

#### 5.2 Input Component
**Required:**
- Label and hint text support
- Error state with message
- Consistent styling
- Accessible (aria-describedby for hints/errors)

**Acceptance Criteria:**
- [ ] All inputs use Input component
- [ ] Error states are visually clear
- [ ] Screen reader compatible

#### 5.3 Card Component
**Required:**
- Variants: stat, info, action
- Consistent padding, borders, shadows
- Hover states where appropriate

**Acceptance Criteria:**
- [ ] All cards use Card component
- [ ] Consistent visual appearance
- [ ] Dark theme compatible

#### 5.4 Toast Component
**Required:**
- Types: success, error, warning, info
- Auto-dismiss with configurable duration
- Dismiss button
- Stack multiple toasts
- Accessible announcements

**Acceptance Criteria:**
- [ ] Toasts appear for key events
- [ ] Auto-dismiss works
- [ ] Can be manually dismissed
- [ ] Screen reader announces

#### 5.5 Skeleton Component
**Required:**
- Match card, stat, list layouts
- Shimmer animation
- Composable for different layouts

**Acceptance Criteria:**
- [ ] Skeletons available for all layouts
- [ ] Smooth animation
- [ ] Easy to compose

---

### Phase 6: Rank-Aware Benchmarks

#### 6.1 Benchmark Data Model
**Required:**
- Store rank benchmarks in database or config
- Initial estimates for Bronze through SSL
- Per-metric benchmarks (goals, assists, boost, etc.)

**Acceptance Criteria:**
- [ ] Benchmark data accessible via API
- [ ] All ranks have benchmarks
- [ ] All key metrics covered

#### 6.2 Benchmark Comparison in Dashboard
**Required:**
- Show user stats compared to rank average
- Visual indicator: above/below/on par
- Context: "Your boost: 48 BCPM (Diamond avg: 45)"

**Acceptance Criteria:**
- [ ] Comparisons shown on dashboard
- [ ] Clear visual indicators
- [ ] Helpful context provided

#### 6.3 Benchmark Comparison in Insights
**Required:**
- Insights reference rank benchmarks
- "Your shooting is 15% (Diamond avg: 18%) — room to improve"
- Severity tied to deviation from benchmark

**Acceptance Criteria:**
- [ ] Insights include benchmark context
- [ ] Severity reflects deviation
- [ ] Actionable recommendations

---

### Phase 7: Multi-Game Trending

#### 7.1 Real Trend Data
**Current:** Trends page shows mock data.
**Required:**
- API endpoint for trend data over time
- Metrics: win rate, key stats, mechanics counts
- Time ranges: 7 days, 30 days, 90 days, all time

**Acceptance Criteria:**
- [ ] Real data from user's replays
- [ ] Multiple time ranges work
- [ ] Empty state when insufficient data

#### 7.2 Trend Visualization
**Required:**
- Line charts for metrics over time
- Clear axis labels and legends
- Responsive to screen size
- Highlight improvements and regressions

**Acceptance Criteria:**
- [ ] Charts render correctly
- [ ] Trends are visually clear
- [ ] Mobile-friendly

#### 7.3 Progress Indicators
**Required:**
- Show improvement/regression arrows
- "Up 5% this week" style callouts
- Celebrate milestones

**Acceptance Criteria:**
- [ ] Directional indicators visible
- [ ] Percentage changes calculated
- [ ] Positive framing for improvements

---

### Phase 8: Cause-Effect Insights

#### 8.1 Enhanced Insight Generation
**Current:** "Shooting is 15% — focus on placement"
**Required:**
- Break down contributing factors
- Specific examples from replay data
- Concrete recommendations

**Example:**
```
Shooting Analysis (15%):
- 4 of 7 shots from >2200 UU (too far)
- 2 shots at >50° angle (low probability)
- Recommendation: Move inside 2000 UU before shooting
```

**Acceptance Criteria:**
- [ ] Insights explain WHY, not just WHAT
- [ ] Specific data points cited
- [ ] Actionable recommendations provided

#### 8.2 Insight Priority Ranking
**Required:**
- Rank insights by impact on improvement
- Show most impactful first
- Visual severity indicators

**Acceptance Criteria:**
- [ ] Insights sorted by priority
- [ ] Visual hierarchy clear
- [ ] Most impactful highlighted

#### 8.3 Session Recap Feature
**Required:**
- After 3+ coach messages, offer "Generate Summary"
- Structured output: strengths, weaknesses, action items
- Shareable format

**Acceptance Criteria:**
- [ ] Summary available after threshold
- [ ] Structured with clear sections
- [ ] Can be copied/shared

---

## Technical Constraints

### Frontend
- Next.js 14 with App Router
- Tailwind CSS for styling
- TypeScript strict mode
- Must support dark theme

### Backend
- FastAPI with existing router structure
- PostgreSQL via SQLAlchemy
- Must maintain backwards compatibility
- Rate limiting must be respected

### Performance
- Dashboard load < 2 seconds
- Coach streaming latency < 500ms to first token
- No blocking renders during data fetch

### Accessibility
- WCAG 2.1 AA compliance
- Keyboard navigable
- Screen reader compatible
- Color contrast ratios met

---

## Success Metrics

| Metric | Current (Est.) | Target |
|--------|----------------|--------|
| Signup → First Upload | 30% | 70% |
| First Upload → 3rd Upload | 20% | 50% |
| Free → Pro Conversion | <1% | 5% |
| Coach Engagement (Pro) | Unknown | 3+ sessions/week |
| Dashboard Return Rate | Unknown | 40% weekly |

---

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| Streaming adds complexity | Graceful fallback to non-streaming |
| Benchmark data is estimated | Document as estimates, refine with real data |
| Tour annoys users | "Skip" option, don't repeat |
| Component refactor breaks things | Incremental migration, test coverage |

---

## Dependencies

- Claude API for coach streaming (existing)
- Stripe for subscription status (existing)
- Recharts for trend visualization (existing)

---

## Timeline

| Phase | Duration | Deliverables |
|-------|----------|--------------|
| 1 | 1 day | Critical fixes live |
| 2 | 1 day | Error handling complete |
| 3 | 1 day | Onboarding and landing page |
| 4 | 1 day | Streaming coach |
| 5 | 2 days | UI component library |
| 6 | 1 day | Benchmarks integrated |
| 7 | 1 day | Real trending data |
| 8 | 1 day | Enhanced insights |

**Total: ~9 days of focused work**

---

## Appendix: User Journey Map

```
Landing Page
    ↓
[Sign Up with Discord/Google]
    ↓
Dashboard (Empty State)
    ↓
"Upload your first replay" prompt
    ↓
[Upload .replay file]
    ↓
Processing (with progress indicator)
    ↓
Success Toast → View Replay
    ↓
Replay Detail (7 tabs of analysis)
    ↓
Explore Dashboard (real stats now)
    ↓
Try Coach (1 free message)
    ↓
"Unlock unlimited coaching for $10/mo"
    ↓
[Upgrade] → Stripe Checkout
    ↓
Pro User → Full Coach Access
```

---

## Approval

- [ ] Product Owner
- [ ] Engineering Lead
- [ ] Codex Review (Mandatory)
