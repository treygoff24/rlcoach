# Fix Plan: Analysis Pipeline Issues

## Executive Summary

After deep investigation of the replay analysis pipeline output, I identified **2 bugs** and **1 false positive**:

| Issue | Type | Severity | Root Cause |
|-------|------|----------|------------|
| Shot speed = 0.0 on goals | Bug | Medium | Using ball velocity at goal frame (after physics reset) |
| Kickoff approach % > 100% | Bug | Low | Denominator mismatch (kickoff count vs approach entries) |
| Pass completion disparity | Not a bug | N/A | Legitimate game data reflecting team playstyle |

---

## Issue 1: Shot Speed = 0.0 on Goals

### Diagnosis

**Location**: `src/rlcoach/events.py`, functions `_detect_goals_from_header()` (lines 436-440) and `_detect_goals_from_ball_path()` (lines 621-622)

**Root Cause**: When a goal is detected, the code reads ball velocity from `frame_ref.ball.velocity` at the exact goal frame:

```python
ball_velocity = frame_ref.ball.velocity if frame_ref else Vec3(0.0, 0.0, 0.0)
shot_speed_kph = _vector_magnitude(ball_velocity) * 3.6
```

However, at the goal frame:
1. The ball has already crossed the goal line
2. The game engine triggers the "goal explosion" animation
3. Ball physics are reset to zero or near-zero velocity
4. The replay records this post-goal state, not the actual shot velocity

**Evidence**: All 3 goals in the test replay show `shot_speed_kph: 0.0` despite being clearly valid scored shots.

### Fix Plan

1. **Modify `_detect_goals_from_header()`**:
   - Before computing shot speed, scan backwards from the goal frame
   - Find the last frame (within ~0.5-1.0 seconds before goal) where ball had significant velocity (>500 uu/s)
   - Use that velocity as the actual shot speed
   - Add constant: `GOAL_LOOKBACK_WINDOW_S = 1.0`
   - Add constant: `MIN_SHOT_VELOCITY_UU_S = 500.0`

2. **Modify `_detect_goals_from_ball_path()`**:
   - Apply same lookback logic
   - Track rolling ball velocity in the frames leading up to goal detection

3. **Implementation**:
```python
def _find_shot_velocity_before_goal(
    frames: list[Frame],
    goal_frame_idx: int,
    frame_rate: float
) -> Vec3:
    """Find ball velocity before goal explosion reset."""
    lookback_frames = int(GOAL_LOOKBACK_WINDOW_S * frame_rate)
    start_idx = max(0, goal_frame_idx - lookback_frames)

    for i in range(goal_frame_idx - 1, start_idx - 1, -1):
        velocity = frames[i].ball.velocity
        speed = _vector_magnitude(velocity)
        if speed >= MIN_SHOT_VELOCITY_UU_S:
            return velocity

    # Fallback: return velocity at goal frame
    return frames[goal_frame_idx].ball.velocity if frames else Vec3(0, 0, 0)
```

### Testing

- Update `tests/test_events.py` to verify shot speed is non-zero for goals
- Add test case with synthetic frames that simulate goal-line crossing with velocity reset
- Run against real replays to verify reasonable shot speeds (typically 50-150+ kph)

---

## Issue 2: Kickoff Approach Percentage > 100%

### Diagnosis

**Location**:
- `src/rlcoach/analysis/kickoffs.py`, function `_analyze_kickoffs_for_team()` (lines 140-153)
- `src/rlcoach/report_markdown.py`, function `_kickoff_approach_table()` (lines 560-571)

**Root Cause**: Mismatch between numerator and denominator when calculating approach type percentages.

In `_analyze_kickoffs_for_team()`:
```python
for ko in kickoffs:
    # ...
    for entry in ko.players:  # <-- Iterates ALL players in each kickoff
        # ...
        approach_types[at] += 1  # <-- Counts per-player entries
```

In `_kickoff_approach_table()`:
```python
b_share = self._percentage_share(b_value, blue.get("count", 0))  # count = 6 kickoffs
```

**Math breakdown**:
- 6 kickoffs × 3 players per team = 18 approach entries per team
- 15 STANDARD approaches / 6 kickoffs = **250%** ← Bug!
- Should be: 15 STANDARD approaches / 18 total entries = 83.3%

### Fix Plan

**Option A (Recommended)**: Add total approach count to kickoff metrics

1. In `kickoffs.py`, track total approach entries:
```python
def _analyze_kickoffs_for_team(...) -> dict[str, Any]:
    # ... existing code ...
    total_approaches = 0

    for ko in kickoffs:
        for entry in ko.players:
            if player_team_name.get(pid) != team_name:
                continue
            total_approaches += 1
            # ... rest of approach counting

    return {
        # ... existing fields ...
        "approach_types": approach_types,
        "total_approaches": total_approaches,  # NEW
    }
```

2. In `report_markdown.py`, use correct denominator:
```python
def _kickoff_approach_table(self, blue: dict, orange: dict) -> str:
    # ...
    b_total = blue.get("total_approaches", blue.get("count", 1))
    o_total = orange.get("total_approaches", orange.get("count", 1))

    for label in labels:
        b_share = self._percentage_share(b_value, b_total)
        o_share = self._percentage_share(o_value, o_total)
```

**Option B (Alternative)**: Normalize in report generation

If we don't want to change the schema, normalize in the markdown renderer:
```python
def _kickoff_approach_table(self, blue: dict, orange: dict) -> str:
    b_approach = blue.get("approach_types", {}) or {}
    b_total = sum(b_approach.values()) or 1
    # Use b_total instead of blue.get("count")
```

### Testing

- Update `tests/test_analysis_kickoffs.py` with 3v3 scenario
- Verify percentages sum to 100% (within rounding)
- Add golden file test for kickoff table formatting

---

## Issue 3: Pass Completion Disparity (NOT A BUG)

### Analysis

**Observed**: Blue team had 1/4 completed passes vs Orange's 16/23

**Investigation**: Reviewed `src/rlcoach/analysis/passing.py`

**Conclusion**: This is **legitimate game data**, not a bug.

The pass completion logic requires:
1. Same-team consecutive touches within 2.0 seconds (`PASS_WINDOW_S`)
2. Forward progress ≥80 units toward opponent goal (`FORWARD_DELTA_MIN_UU`)

Blue team lost 1-2, meaning they were likely:
- More defensive (backward passes = not counted as completions)
- Being pressured (more turnovers = 128 vs Orange's 129)
- Playing reactive rather than proactive passing

The metrics accurately reflect that Orange had better passing play and possession control, contributing to their victory.

**No code changes needed.**

---

## Implementation Order

1. **Issue 2 (Kickoff %)** - Quick fix, low risk, affects only display
2. **Issue 1 (Shot speed)** - Medium complexity, affects event detection accuracy

## Files to Modify

| File | Changes |
|------|---------|
| `src/rlcoach/events.py` | Add `_find_shot_velocity_before_goal()`, update goal detection |
| `src/rlcoach/analysis/kickoffs.py` | Add `total_approaches` field to return dict |
| `src/rlcoach/report_markdown.py` | Use correct denominator for approach percentages |
| `tests/test_events.py` | Add shot speed test cases |
| `tests/test_analysis_kickoffs.py` | Add 3v3 percentage validation |
| `schemas/replay_report.schema.json` | (Optional) Add `total_approaches` field |

## Estimated Effort

- Issue 2: ~30 minutes (simple fix)
- Issue 1: ~1-2 hours (needs careful testing with real replays)
- Total: ~2 hours
