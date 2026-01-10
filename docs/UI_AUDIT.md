# RLCoach Dashboard UI/UX Audit

**Date:** 2026-01-10
**Status:** COMPLETE - Ready for fixes
**Auditor:** Claude (Autonomous Build)

---

## Summary

**Critical Issues:** 2
**High Priority:** 4
**Medium Priority:** 6
**Low Priority:** 3

---

## Page Audits

### 1. Home Page

**Spec Requirements:**
- Hero view: mechanics breakdown with rank comparisons
- "You hit 47 flip resets this season — top 3% for Diamond"
- Topline stats with visual hierarchy
- Core fundamentals large: Goals, assists, saves, shots, demos
- Efficiency metrics smaller: Boost/100, avg speed, time supersonic

**Issues Found:**
- 🔴 **CRITICAL:** Home link goes to public landing page instead of authenticated dashboard
- 🔴 **CRITICAL:** No dashboard home page exists for logged-in users
- Need to create a new `/dashboard` or modify `/` to show dashboard when authenticated

---

### 2. Replays Page

**Spec Requirements:**
- All uploaded replays, sortable/filterable

**Issues Found:**
- 🟠 **HIGH:** Replay names show hash IDs (6dcacb7922ae62da4a3...) instead of readable format
- 🟠 **HIGH:** Map names show internal codes (EuroStadium_P, mall_day_p) instead of friendly names
- 🟡 **MEDIUM:** No column sorting controls visible
- 🟡 **MEDIUM:** Some results show "--" (missing data for 3 replays)
- 🟢 **LOW:** All dates show same day (seed script issue, not UI)

**Working:**
- ✅ Shows 50 replays with pagination
- ✅ Playlist badges (DOUBLES, STANDARD)
- ✅ W/L results with scores (W 2-1, L 4-5)
- ✅ Date/time display
- ✅ Analyzed status badge
- ✅ Filter tabs (All, Analyzed, Processing)

---

### 3. Replay Detail Page

**Spec Requirements:**
- 7 tabs: Overview, Mechanics, Boost, Positioning, Timeline, Defense, Offense
- Deep dive on single game
- Each tab must look crispy and sharp
- Clean data visualization, thoughtful hierarchy

**Issues Found:**
- 🔴 **CRITICAL:** All player stats showing 0s (Score, Goals, Assists, Saves, Shots)
- 🔴 **CRITICAL:** Mechanics tab all zeros (Wave Dashes, Half Flips, Speed Flips, Aerials, Demos)
- 🔴 **CRITICAL:** Boost tab all dashes (Avg Boost, Time Empty, Time Full, Pads, Stolen)
- 🟠 **HIGH:** Title shows hash ID instead of readable name
- 🟠 **HIGH:** Map name shows internal code
- 🟡 **MEDIUM:** No team colors for orange team players in scoreboard

**Working:**
- ✅ All 7 tabs present (Overview, Mechanics, Boost, Positioning, Timeline, Defense, Offense)
- ✅ Game result display (Blue Team 8 vs Orange Team 4)
- ✅ Victory badge
- ✅ Scoreboard with player list
- ✅ "(you)" label on user's player
- ✅ Team color dots

---

### 4. Sessions Page

**Spec Requirements:**
- Replays grouped by play session (30-min gap threshold)

**Issues Found:**
- 🟡 **MEDIUM:** Avg Goals/Saves showing 0.0 (stats aggregation issue)
- 🟢 **LOW:** All replays in one session (seed script date issue, not UI)

**Working:**
- ✅ Sessions display with date header (Friday, Jan 9)
- ✅ Game count (118 games)
- ✅ Duration (695 minutes)
- ✅ W-L record (82-31)
- ✅ Win rate percentage (69%)

---

### 5. Trends Page

**Spec Requirements:**
- Stats over time with flexible axis
- Axis options: Session-based (default), Time-based, Replay-based

**Issues Found:**
- 🔴 All stats 0.0 due to data issue
- 🟡 **MEDIUM:** No axis toggle (session/time/replay) as spec requires
- 🟡 **MEDIUM:** Chart x-axis shows numbers instead of dates

**Working:**
- ✅ Stat tabs (Goals, Saves, Assists, Shots, Boost/min)
- ✅ Time range tabs (7 Days, 30 Days, 90 Days, All Time)
- ✅ Chart visualization
- ✅ Summary cards (Current, Average, Best, Worst)

---

### 6. Compare Page

**Spec Requirements:**
- Two modes:
  1. Rank comparison: Your stats vs your rank average, vs next rank up
  2. Self comparison: Current period vs previous

**Issues Found:**
- 🔴 All stats 0.0 due to data issue
- 🟡 **MEDIUM:** Stat names use snake_case (goals_per_game vs "Goals per Game")
- 🟡 **MEDIUM:** Diff indicators could use color coding (red for negative)

**Working:**
- ✅ Two tabs (Vs Your Rank, Vs Yourself)
- ✅ Rank comparison header (Comparing against: Gold I)
- ✅ Stats grid with multiple metrics
- ✅ Rank average values
- ✅ Diff from rank average

---

### 7. Settings Page

**Spec Requirements:**
- Profile, linked accounts, preferences

**Issues Found:**
- 🟢 **LOW:** Missing Epic Games account option (spec mentioned it)

**Working:**
- ✅ Profile section (name, email)
- ✅ Subscription section (Pro Plan, Manage button)
- ✅ Linked Accounts (Discord connected, Steam/Google options)
- ✅ Preferences (Session Gap setting - 30 min default)
- ✅ Data section (Export Data, Delete Account)

---

## Global Issues

- 🔴 **CRITICAL:** PlayerGameStats not storing actual values from replay analysis
- 🟠 **HIGH:** Map name mapping needed (internal code → friendly name)
- 🟠 **HIGH:** Replay ID display needs improvement

---

## Root Cause Analysis

### Player Stats All Zeros

The seed script (`scripts/seed_dev_replays.py`) creates PlayerGameStats records but the `core_stats` data from the report may not be populating correctly. Need to investigate:

1. Does `generate_report()` return `core_stats` with actual values?
2. Is the seed script correctly extracting and storing stats?
3. Is the frontend correctly fetching stats from the API?

---

## Fix Priority Queue

### Phase 1 - Critical (Blocking Issues)

1. **Fix PlayerGameStats data population** - Root cause of all zeros
2. **Create authenticated dashboard home page** - Missing core feature

### Phase 2 - High Priority (Major UX Issues)

3. **Add map name mapping** - EuroStadium_P → "Urban Central"
4. **Improve replay name display** - Show map + date/time instead of hash

### Phase 3 - Medium Priority (Polish)

5. Add sorting to Replays table
6. Add axis toggle to Trends page
7. Fix stat name formatting (snake_case → Title Case)
8. Add color coding to Compare diff values
9. Fix Sessions avg goals/saves calculation

### Phase 4 - Low Priority (Nice to Have)

10. Add Epic Games linked account option
11. Additional visual polish

---

## Next Steps

1. Investigate and fix the player stats data issue
2. Create authenticated dashboard home page
3. Add map name mapping utility
4. Iterate on UX improvements
5. Get Gemini review of completed fixes
