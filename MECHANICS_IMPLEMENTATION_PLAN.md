# Implementation Plan: Extended Mechanics Detection

> Based on `MECHANICS_SPEC.md`. Extends `src/rlcoach/analysis/mechanics.py` with 12 new mechanics.

---

## Current Status

**Phase**: 0.5 - Codebase Understanding
**Working on**: Reading existing mechanics.py structure
**Cross-agent reviews completed**: Spec review (Codex), Plan review (Codex)
**Blockers**: None
**Runtime**: 0 min

---

## Phase 0.5: Codebase Understanding (Complete)

**Objective:** Understand existing mechanics detection patterns and integration points.

**Dependencies:** None

**Tasks:**
- [x] Review `src/rlcoach/analysis/mechanics.py` structure
- [x] Understand `PlayerMechanicsState` state machine
- [x] Review `detect_mechanics_for_player()` frame iteration loop
- [x] Identify where to add new state fields
- [x] Review `events/touches.py` for touch detection integration
- [x] Check physics constants for threshold values
- [x] Create feature branch

**Key Findings:**
- State machine resets on landing (lines 221-228)
- Frame iteration uses prev_frame pattern for derivatives
- Existing thresholds in module-level constants (lines 81-94)
- Touch detection available via `detect_touches()` from events/touches.py
- Ball data available in `Frame.ball` (BallFrame with position, velocity)

**Acceptance criteria:** Feature branch created, code patterns understood

**Estimated complexity:** Simple

---

## Phase 1: Foundation & Fast Aerial

**Objective:** Add new enum values, extend state tracking, implement fast aerial detection with proper boost tracking.

**Dependencies:** Phase 0.5

**Tasks:**
- [ ] Add new `MechanicType` enum values (12 new types)
- [ ] Extend `MechanicEvent` dataclass with new optional fields (`ball_position`, `ball_velocity_change`, `boost_used`)
- [ ] Extend `PlayerMechanicsState` with ALL new tracking fields from spec:
  - `first_jump_time`, `boost_at_first_jump`, `boost_used_since_jump` (fast aerial)
  - `dribble_start_time`, `is_dribbling`, `ball_speed_at_dribble_start` (dribble)
  - `last_aerial_touch_time`, `flip_available_from_reset` (flip reset)
  - `air_roll_start_time`, `is_air_rolling` (air roll)
  - `power_slide_start_time`, `is_power_sliding` (power slide)
  - `last_ceiling_touch_time` (ceiling shot)
  - `aerial_touch_count_since_ground`, `first_aerial_touch_time`, `wall_bounce_detected` (double touch)
- [ ] Add ALL threshold constants from spec
- [ ] Implement `rotation_to_up_vector()` helper function
- [ ] Implement `normalize_angle()` for angle wrapping
- [ ] Implement fast aerial detection with FULL spec logic:
  - Track `first_jump_time` on jump
  - Track boost consumption: `boost_delta = prev_boost - current_boost`
  - Check boost window: if `boost_delta > 0` within 0.3s of jump
  - Check second jump: double_jump OR flip within 0.5s of first jump
  - Check height: > 300 UU within 1.0s of first jump
  - Emit FAST_AERIAL with `boost_used` field populated
- [ ] Write unit tests for fast aerial using synthetic frames

**Files to modify:**
- `src/rlcoach/analysis/mechanics.py` (main changes)

**Acceptance criteria:**
- [ ] Fast aerial detected when: jump + boost usage within 0.3s + second jump within 0.5s, height > 300 UU within 1.0s
- [ ] `boost_used` field correctly populated
- [ ] New enum values compile without errors
- [ ] Existing tests still pass
- [ ] New test for fast aerial passes

**Estimated complexity:** Moderate (50 min)

---

## Phase 2: Flip Reset & Air Roll

**Objective:** Implement flip reset detection with underside contact and air roll tracking with proper state management.

**Dependencies:** Phase 1 (state fields, helper functions)

**Tasks:**
- [ ] Implement underside contact detection (dot product approach):
  - Compute car up vector: `up = rotation_to_up_vector(car.rotation)`
  - Compute ball-to-car vector: `ball_to_car = normalize(car.position - ball.position)`
  - Check dot product: `dot(up, ball_to_car) > 0.7`
  - Check proximity: `distance < 120.0` UU
- [ ] Add `flip_available_from_reset` state management:
  - Precondition: `has_flipped = True` (flip already consumed)
  - Set flag on underside contact
  - Reset flag on landing OR when flip is used
  - Enforce 2.0s window between contact and reset flip
- [ ] Modify flip detection to emit FLIP_RESET when reset flip used
- [ ] Implement air roll detection with proper start/end tracking:
  - Compute roll rate with `normalize_angle()` for wrapping
  - Exclude flip-induced rotation: skip air roll check for 0.2s after flip
  - Track start condition: first frame where `|roll_rate| > 2.0 rad/s` while airborne
  - Track end condition: `|roll_rate| < threshold` OR landing OR flip starts
  - Emit AIR_ROLL with duration only if > 0.3s
- [ ] Write unit tests for flip reset (positive and negative cases)
- [ ] Write unit tests for air roll (positive and negative cases)

**Files to modify:**
- `src/rlcoach/analysis/mechanics.py`

**Acceptance criteria:**
- [ ] Flip reset detected when: underside contact (dot > 0.7, distance < 120) after flip consumed, followed by flip within 2.0s
- [ ] Flip reset NOT detected if flip not consumed first
- [ ] `flip_available_from_reset` correctly reset on landing and flip use
- [ ] Air roll detected when: roll rate > 2.0 rad/s sustained > 0.3s while airborne
- [ ] Air roll NOT detected during flip rotation spike
- [ ] Air roll duration field populated correctly
- [ ] Tests for both mechanics pass

**Estimated complexity:** Complex (60 min)

---

## Phase 3: Dribble & Flick Detection

**Objective:** Implement dribble tracking and flick detection with proper car-local transforms.

**Dependencies:** Phase 1 (state fields)

**Tasks:**
- [ ] Implement dribble envelope checking with car-local transform:
  - Compute ball-to-car offset: `dx, dy, dz`
  - Transform to car-local using rotation (optional for v1: use world coords + heading)
  - Check horizontal: `sqrt(dx² + dy²) < 100` UU
  - Check vertical: `90 < dz < 180` UU
  - Check car grounded: `car.z < 50` UU
  - Check relative velocity: `|ball_vel - car_vel| < 300` UU/s
- [ ] Add dribble start/end tracking:
  - Record `dribble_start_time` and `ball_speed_at_dribble_start` on entry
  - Emit DRIBBLE at end with duration (only if > 0.5s)
  - Reset dribble state on exit
- [ ] Implement generic flick detection:
  - Check player was in dribble state
  - Record `pre_flip_ball_speed = |ball.velocity|` at flip start
  - Within 0.3s, compute `ball_velocity_change = |post_speed| - |pre_speed|`
  - If `ball_velocity_change > 500` UU/s, emit FLICK with delta
- [ ] Implement musty flick detection:
  - Check player was in dribble state
  - Check backward flip (existing direction detection)
  - Compute ball Z velocity delta: `post_z - pre_z`
  - If `z_delta > 800` UU/s, emit MUSTY_FLICK
- [ ] Write unit tests for dribble (positive and negative cases)
- [ ] Write unit tests for generic flick
- [ ] Write unit tests for musty flick

**Files to modify:**
- `src/rlcoach/analysis/mechanics.py`

**Acceptance criteria:**
- [ ] Dribble detected when: ball in envelope for > 0.5s, car grounded
- [ ] Dribble NOT detected when car is on wall (z > 50)
- [ ] Flick detected when: ball departs dribble during flip with velocity gain > 500 UU/s
- [ ] Musty flick detected when: backward flip from dribble with ball Z velocity gain > 800 UU/s
- [ ] Tests pass

**Estimated complexity:** Moderate (50 min)

---

## Phase 3.5: Early Real-Replay Validation

**Objective:** Test flip reset, air roll, dribble, and flick detection with real replays to catch threshold issues early.

**Dependencies:** Phase 3

**Tasks:**
- [ ] Run mechanics analysis on 2-3 real replay files
- [ ] Log detected events for flip reset, air roll, dribble, flick
- [ ] Verify no crashes
- [ ] Check for obvious false positives/negatives
- [ ] Tune thresholds if needed (document any changes)

**Files to modify:**
- `src/rlcoach/analysis/mechanics.py` (threshold tuning only)

**Acceptance criteria:**
- [ ] Real replay processing succeeds without crashes
- [ ] No obvious false positives in output
- [ ] Thresholds seem reasonable for observed data

**Estimated complexity:** Simple (20 min)

---

## Phase 4: Touch Detection Integration & Ceiling Shot

**Objective:** Integrate touch detection for ball contact mechanics, implement ceiling shot.

**Dependencies:** Phase 1 (state fields)

**Tasks:**
- [ ] **CRITICAL: Decide touch detection approach:**
  - Option A: Import `detect_touches()` from `events/touches.py` and pre-compute touches
  - Option B: Use inline proximity detection (< 200 UU) per frame
  - **Decision:** Use proximity detection inline (simpler, consistent with existing mechanics.py)
- [ ] Implement ceiling contact tracking: `car.z > 1900` UU
- [ ] Implement ceiling shot detection:
  - Record `last_ceiling_touch_time` on ceiling contact
  - On ball touch while airborne within 3.0s window, emit CEILING_SHOT
- [ ] Implement power slide detection:
  - Check car is grounded
  - Compute car forward vector: `forward = (cos(yaw), sin(yaw), 0)`
  - Compute sideways velocity: `sideways = velocity - dot(velocity, forward) * forward`
  - If `|sideways| > 500` UU/s for > 0.2s, emit POWER_SLIDE with duration
- [ ] Write unit tests for ceiling shot
- [ ] Write unit tests for power slide

**Files to modify:**
- `src/rlcoach/analysis/mechanics.py`

**Acceptance criteria:**
- [ ] Ceiling shot detected when: car Z > 1900 UU followed by aerial ball touch within 3.0s
- [ ] Power slide detected when: sideways velocity > 500 UU/s for > 0.2s while grounded
- [ ] Tests pass

**Estimated complexity:** Moderate (45 min)

---

## Phase 5A: Touch-Based Mechanics (Ground Pinch, Double Touch, Redirect)

**Objective:** Implement mechanics that require ball contact detection.

**Dependencies:** Phase 4 (touch detection approach decided)

**Tasks:**
- [ ] Implement ground pinch detection:
  - On ball touch (proximity < 200 UU), check ball Z < 100 UU
  - Record `pre_touch_speed` from previous frame
  - Compute `velocity_delta = |post_speed| - |pre_speed|`
  - If `post_speed > 3000` UU/s AND `velocity_delta > 1500` UU/s, emit GROUND_PINCH
- [ ] Implement double touch detection:
  - Track `aerial_touch_count_since_ground` (reset on landing)
  - Track `first_aerial_touch_time` on first aerial touch (car Z > 300 UU)
  - Track `wall_bounce_detected`: ball position near wall between touches
    - Backboard: `|ball.y| > FIELD.BACK_WALL_Y - 200`
    - Side wall: `|ball.x| > FIELD.SIDE_WALL_X - 200`
  - On second aerial touch within 3.0s with wall bounce, emit DOUBLE_TOUCH
- [ ] Implement redirect detection:
  - On aerial touch (car Z > 300 UU), check ball speed > 500 UU/s
  - Compute pre/post touch velocity direction
  - Compute angle: `acos(dot(pre_dir, post_dir))`
  - Check `is_toward_opponent_goal(team, post_velocity)`
  - If angle > 0.785 rad (45°) and toward goal, emit REDIRECT
- [ ] Write unit tests for each mechanic

**Files to modify:**
- `src/rlcoach/analysis/mechanics.py`

**Acceptance criteria:**
- [ ] Ground pinch: ball Z < 100 UU, exit velocity > 3000 UU/s, delta > 1500 UU/s
- [ ] Double touch: two aerial touches with wall bounce between, within 3.0s
- [ ] Redirect: aerial touch changes direction > 45° toward goal, ball speed > 500 UU/s
- [ ] Tests pass

**Estimated complexity:** Complex (50 min)

---

## Phase 5B: Kinematics-Only Mechanics (Stall)

**Objective:** Implement stall detection using only physics state (no touch required).

**Dependencies:** Phase 2 (air roll detection pattern)

**Tasks:**
- [ ] Implement stall detection:
  - Check car is airborne at height > 300 UU
  - Compute roll rate and yaw rate from rotation deltas
  - Check tornado pattern: `|roll_rate| > 3.0` AND `|yaw_rate| > 2.0` AND opposite signs
  - Check hover: `|velocity.z| < 100` UU/s
  - Check low forward speed: `|velocity.xy| < 500` UU/s
  - If all conditions met for > 0.15s, emit STALL
- [ ] Write unit tests for stall (positive and negative cases)

**Files to modify:**
- `src/rlcoach/analysis/mechanics.py`

**Acceptance criteria:**
- [ ] Stall: tornado pattern with near-zero vertical velocity for > 0.15s
- [ ] Stall NOT detected on ground or at low height
- [ ] Tests pass

**Estimated complexity:** Moderate (30 min)

---

## Phase 6: Output Schema & Aggregation (Mandatory)

**Objective:** Update per-player output with new metric counts and durations. Schema updates are REQUIRED.

**Dependencies:** Phases 1-5B (all mechanics implemented)

**Tasks:**
- [ ] Update `analyze_mechanics()` to aggregate new event types
- [ ] Add new keys to per_player output dict (all 14 new keys)
- [ ] Add duration aggregation for air_roll, dribble, power_slide
- [ ] **MANDATORY:** Update JSON schema `schemas/replay_report.schema.json`
- [ ] Write tests for output format

**Files to modify:**
- `src/rlcoach/analysis/mechanics.py`
- `schemas/replay_report.schema.json` (REQUIRED)

**New output keys:**
```python
{
    "fast_aerial_count": int,
    "flip_reset_count": int,
    "air_roll_total_time_s": float,
    "dribble_count": int,
    "dribble_total_time_s": float,
    "flick_count": int,
    "musty_flick_count": int,
    "ceiling_shot_count": int,
    "power_slide_count": int,
    "power_slide_total_time_s": float,
    "ground_pinch_count": int,
    "double_touch_count": int,
    "redirect_count": int,
    "stall_count": int
}
```

**Acceptance criteria:**
- [ ] All 14 new keys appear in per_player output
- [ ] Duration fields sum correctly
- [ ] Schema validates (run schema validation)
- [ ] Tests pass

**Estimated complexity:** Moderate (35 min)

---

## Phase 7: Integration & Regression Testing

**Objective:** Verify full integration with real replays, no regressions.

**Dependencies:** Phase 6

**Tasks:**
- [ ] Run full test suite (`make test`)
- [ ] Process real replay files and verify no crashes
- [ ] Verify existing mechanics still detected correctly
- [ ] Check performance (< 5ms per 1000 frames)
- [ ] Fix any issues found

**Files to modify:**
- Any files with bugs discovered

**Acceptance criteria:**
- [ ] All tests pass (currently 391+)
- [ ] Real replay processing succeeds
- [ ] No regressions in existing mechanics
- [ ] Performance target met

**Estimated complexity:** Simple (30 min)

---

## Phase 8: Report Markdown Updates

**Objective:** Add new mechanics to markdown report output.

**Dependencies:** Phase 6 (output schema complete)

**Tasks:**
- [ ] Update `report_markdown.py` to include new mechanics in player stats
- [ ] Add section for advanced mechanics if appropriate
- [ ] Update golden test files for new markdown format

**Files to modify:**
- `src/rlcoach/report_markdown.py`
- `tests/goldens/*.md` (update expected output)

**Acceptance criteria:**
- [ ] New mechanics appear in markdown report
- [ ] Golden tests pass

**Estimated complexity:** Simple (25 min)

---

## Phase 9: Final Review & Cleanup

**Objective:** Code review and cleanup.

**Dependencies:** Phase 8

**Tasks:**
- [ ] Run code-reviewer agent
- [ ] Fix any issues found
- [ ] Remove debug statements
- [ ] Verify test coverage > 80% for new code
- [ ] Run `make fmt` and `make lint`

**Acceptance criteria:**
- [ ] Code review passes
- [ ] Lint/format clean
- [ ] All tests pass
- [ ] Coverage target met

**Estimated complexity:** Simple (20 min)

---

## Risk Factors

1. **Flip reset detection accuracy:** Underside contact via dot product may need threshold tuning with real replays
2. **Air roll false positives:** Flip-induced rotation could trigger air roll if exclusion window is wrong
3. **Dribble edge cases:** Wall dribbles excluded but edge detection near walls may be noisy
4. **Performance:** Many new checks per frame; need to verify < 5ms/1000 frames target
5. **Double touch wall detection:** Ball position near wall ≠ wall contact; may have false positives
6. **State reset bugs:** `flip_available_from_reset`, `is_dribbling`, `is_air_rolling` must be reset correctly on landing/events
7. **Orientation math:** Up vector, roll/yaw wrapping, car-local coords are easy to get subtly wrong

## Mitigation

- Test with real replays early (Phase 3.5)
- Tune thresholds based on observed behavior
- Add logging for debugging false positives during development
- Profile performance in Phase 7
- Explicit state reset logic in each phase's tasks

---

## Total Estimated Time

| Phase | Complexity | Time |
|-------|------------|------|
| 0.5 | Simple | 15 min |
| 1 | Moderate | 50 min |
| 2 | Complex | 60 min |
| 3 | Moderate | 50 min |
| 3.5 | Simple | 20 min |
| 4 | Moderate | 45 min |
| 5A | Complex | 50 min |
| 5B | Moderate | 30 min |
| 6 | Moderate | 35 min |
| 7 | Simple | 30 min |
| 8 | Simple | 25 min |
| 9 | Simple | 20 min |

**Total: ~7 hours**
